"""consensus.py — MLB Edge-E7.11: a multi-source prospect-ranking CONSENSUS (pure, no IO).

E8.0 ranks off FanGraphs FV alone. This module adds a second and (optionally) further independent
scouting sources, aggregates them into a consensus, and — the part that is actually worth having —
locates where the sources DISAGREE with each other and where OUR translated line disagrees with all
of them.

    SOURCES (each contributes a numeric rank, keyed on MLBAM)
      FanGraphs THE BOARD  — E7.7, overall_rank + org_rank + FV        [ingested]
      MLB Pipeline         — E7.11, Top 100 + 30 org Top 30s           [ingested]
      Baseball America · Keith Law · ESPN/McDaniel · Baseball Prospectus · Prospects Live
                           — MANUAL hand-keyed CSV, never scraped      [operator-supplied]
                └──────────────── consensus ────────────────┘
                                     vs
                     OUR E7.3/E7.3p MiLB→MLB translated line

🔒 HONEST FRAME (`best_alpha = 0`). **A consensus is a DESCRIPTION, not a claim.** Nothing here
asserts that the consensus beats any single source, that our line beats the consensus, or that a
disagreement is an edge. No accuracy claim was tested and none is made — that question is E7.8's
(which found FV's lift is real for ARMS and redundant for BATS), and it was answered about FV, not
about this aggregate. What a consensus buys is *robustness to single-source idiosyncrasy*, and
what a disagreement buys is *a shortlist of players worth a second look*.

⚠️ THREE MODELLING DECISIONS THAT LOOK LIKE DETAILS AND ARE NOT
---------------------------------------------------------------
**1. PARTIAL COVERAGE IS AVERAGED OVER, NEVER IMPUTED.** A source that publishes a Top 100 has said
nothing whatsoever about player #340 — it has not ranked him 101st. So the consensus is the mean of
the ranks that EXIST, and `n_sources` travels beside it. Imputing "unranked ⇒ rank = list length +
1" would fabricate an opinion the source never gave, and would systematically punish players in
organizations a source happens to cover less.

**2. A 1-SOURCE CONSENSUS IS NOT A CONSENSUS.** Averaging one number returns that number. So every
row carries `n_sources` and `consensus_confidence`, and the ordering is available filtered to
`--min-sources`. This is stated loudly because a "consensus rank" column silently backed by a
single source is the most plausible way this table gets misread.

**3. DISAGREEMENT IS A RESIDUAL, NOT A GAP.** `source_rank − consensus_rank` flags the entire top
of the board as "this source is lower" purely because imperfectly-correlated rankings regress
toward each other at the extremes — E8.0 hit exactly this on its first real run (10 of the top 12
flagged). Every disagreement column here is the residual after removing the fitted relationship
(`board_assembly.residual_vs_fit`, the shared instrument).

⚠️ RANK SCOPES ARE NOT INTERCHANGEABLE. An "overall" rank (a Top-100 place) and an "org" rank (a
place within one organization's Top 30) are different measurements: org rank 1 for a bottom-farm
club is not overall rank 1. They are therefore aggregated in SEPARATE scopes — `overall` (deep, ~100
players, several sources) and `org` (wide, ~900+ players, ranked within `org`) — and never mixed
into one average.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from betting_ml.scripts.prospect_board.board_assembly import residual_vs_fit

__all__ = [
    "CONSENSUS_TIERS",
    "ConsensusError",
    "MANUAL_CSV_COLUMNS",
    "PAYWALLED_SOURCES",
    "RankSource",
    "attach_consensus",
    "build_consensus",
    "coverage_table",
    "format_consensus_report",
    "manual_template_frame",
    "normalize_name",
    "resolve_manual_source",
]


class ConsensusError(RuntimeError):
    """A consensus invariant failed — a duplicated key, an empty source, an unusable manual file.

    HARD stop rather than a NULL column: a source that silently contributes nothing looks exactly
    like a source that ranked nobody, and the resulting "consensus" would quietly be one source
    wearing the word consensus.
    """


# Sources that exist behind a paywall or a robots restriction, and are therefore ONLY ever admitted
# as hand-keyed manual files. Named here so the report can label them, and so the code path that
# would scrape them does not exist to be reached for. (Verified 2026-07-29: Prospects Live's
# robots.txt carries `User-agent: ClaudeBot / Disallow: /` plus an `ai-train=no` Content-Signal, and
# its ranking routes 404 anonymously — so it joins the paywalled group despite being "free".)
PAYWALLED_SOURCES: dict[str, str] = {
    "baseball_america": "PAYWALLED — hand-keyed public Top 100; never scraped",
    "keith_law": "PAYWALLED (The Athletic) — hand-keyed public Top 100; never scraped",
    "espn_mcdaniel": "PAYWALLED (ESPN+) — hand-keyed public Top 100; never scraped",
    "baseball_prospectus": "PAYWALLED — hand-keyed public Top 101; never scraped",
    "prospects_live": "ROBOTS-RESTRICTED (ClaudeBot Disallow: /) — hand-keyed only; never scraped",
}

# The schema an operator's hand-keyed file must use. `mlbam_id` is optional but STRONGLY preferred:
# with it the row joins deterministically; without it we fall back to exact normalized name(+org)
# matching against the board universe only, and report every unresolved row (E7.4: no fuzzy leg —
# a name-equality match against the full player universe produced a false positive).
MANUAL_CSV_COLUMNS = ["rank", "player_name", "org", "mlbam_id"]

# Consensus tiers, in overall-rank space. Buckets, not a continuum, because that is how a draft
# board is actually used ("is he a top-25 guy or a top-100 guy") and because the difference between
# consensus 63 and 71 is not a difference any of these sources would defend.
CONSENSUS_TIERS: list[tuple[float, str]] = [
    (10, "Tier 1 (top 10)"),
    (25, "Tier 2 (11-25)"),
    (50, "Tier 3 (26-50)"),
    (100, "Tier 4 (51-100)"),
    (250, "Tier 5 (101-250)"),
    (float("inf"), "Tier 6 (251+)"),
]

# |residual| in rank-percentile points before a source is called a disagreement rather than noise.
# Matches E8.0's DISAGREEMENT_THRESHOLD (15 points on a ~1,300-player percentile) for the same
# reason: below it, the "disagreement" is rank jitter between two lists nobody built to agree.
DISAGREEMENT_THRESHOLD = 15.0


@dataclass
class RankSource:
    """One ranking source: where its rank lives and what kind of rank it is.

    `scope` is load-bearing — `overall` ranks aggregate against each other, `org` ranks aggregate
    within an organization, and the two never mix (see the module docstring).
    """
    name: str
    rank_col: str
    scope: str = "overall"                 # 'overall' | 'org'
    label: str | None = None               # display name; defaults to `name`
    access: str = "ingested"               # 'ingested' | 'manual'
    note: str = ""

    def __post_init__(self) -> None:
        if self.scope not in ("overall", "org"):
            raise ConsensusError(
                f"source {self.name!r} has scope {self.scope!r}; must be 'overall' or 'org'. An "
                f"org rank and an overall rank are different measurements and cannot be averaged."
            )
        self.label = self.label or self.name


# ── Name normalization (for MANUAL files only) ───────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b")


def normalize_name(name: Any) -> str | None:
    """`"José Ramírez Jr."` → `"jose ramirez"`. Accent-folded, punctuation-stripped, suffix-dropped.

    Used ONLY to resolve a hand-keyed manual file, and only as an EXACT match after normalization —
    there is no edit-distance/fuzzy leg anywhere in this module (E7.4 landmine 4). Normalization
    removes spelling *conventions*; it does not guess at spelling *differences*.
    """
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return None
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()
    text = _PUNCT_RE.sub(" ", text)
    text = _SUFFIX_RE.sub(" ", text)
    text = " ".join(text.split())
    return text or None


def manual_template_frame() -> pd.DataFrame:
    """An empty, correctly-columned frame the runner writes as the hand-key template."""
    return pd.DataFrame(columns=MANUAL_CSV_COLUMNS)


def resolve_manual_source(manual: pd.DataFrame, universe: pd.DataFrame, *,
                          source_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach `mlbam_id` to a hand-keyed ranking file. Returns `(resolved, report)`.

    Three DETERMINISTIC legs, in confidence order — and nothing else:
      1. `mlbam_id` supplied in the file          → used verbatim (`id_supplied`).
      2. exact normalized (name, org) in universe → `name_org_exact`.
      3. exact normalized name, UNIQUE in universe→ `name_exact_unique`.

    A name that matches more than one board player is left UNRESOLVED, not arbitrated. Every
    unresolved row is returned in the report for the operator to reconcile by hand — a hand-keyed
    Top 100 with 4 unmatched rows is a 96-player source, and it says so, rather than quietly
    becoming a 100-player source with 4 wrong players in it.
    """
    if manual.empty:
        raise ConsensusError(f"manual source {source_name!r} is EMPTY — nothing to consense over.")
    missing = [c for c in ("rank", "player_name") if c not in manual.columns]
    if missing:
        raise ConsensusError(
            f"manual source {source_name!r} is missing required column(s) {missing}. Expected "
            f"columns: {MANUAL_CSV_COLUMNS} (`mlbam_id` optional but preferred; `org` improves the "
            f"name match)."
        )

    work = manual.copy()
    work["rank"] = pd.to_numeric(work["rank"], errors="coerce")
    work["_name_key"] = work["player_name"].map(normalize_name)
    work["_org_key"] = (work["org"].astype("string").str.strip().str.upper()
                        if "org" in work.columns else pd.Series(pd.NA, index=work.index,
                                                                dtype="string"))
    supplied = (work["mlbam_id"].astype("string").str.strip()
                if "mlbam_id" in work.columns else pd.Series(pd.NA, index=work.index,
                                                             dtype="string"))
    work["mlbam_id"] = supplied.replace({"": pd.NA})
    work["match_method"] = np.where(work["mlbam_id"].notna(), "id_supplied", "unresolved")

    uni = universe.copy()
    uni["_name_key"] = uni["player_name"].map(normalize_name)
    uni["_org_key"] = uni["org"].astype("string").str.strip().str.upper()
    uni = uni[uni["_name_key"].notna() & uni["mlbam_id"].notna()]

    # leg 2 — (name, org), only where the pair is unique in the universe
    by_name_org = (uni.groupby(["_name_key", "_org_key"])["mlbam_id"]
                   .agg(["first", "size"]).reset_index())
    unique_name_org = by_name_org[by_name_org["size"] == 1].set_index(["_name_key", "_org_key"])
    # leg 3 — name alone, only where the name is unique in the universe
    by_name = uni.groupby("_name_key")["mlbam_id"].agg(["first", "size"])
    unique_name = by_name[by_name["size"] == 1]
    ambiguous_names = set(by_name[by_name["size"] > 1].index)

    for idx, row in work[work["mlbam_id"].isna()].iterrows():
        key_name, key_org = row["_name_key"], row["_org_key"]
        if key_name is None:
            continue
        if pd.notna(key_org) and (key_name, key_org) in unique_name_org.index:
            work.at[idx, "mlbam_id"] = unique_name_org.loc[(key_name, key_org), "first"]
            work.at[idx, "match_method"] = "name_org_exact"
        elif key_name in unique_name.index:
            work.at[idx, "mlbam_id"] = unique_name.loc[key_name, "first"]
            work.at[idx, "match_method"] = "name_exact_unique"

    resolved = work[work["mlbam_id"].notna() & work["rank"].notna()].copy()
    resolved["mlbam_id"] = resolved["mlbam_id"].astype(str)
    dupes = resolved["mlbam_id"].duplicated()
    if dupes.any():
        raise ConsensusError(
            f"manual source {source_name!r} resolved {int(dupes.sum())} DUPLICATE mlbam_id(s) — two "
            f"ranked rows became the same player. Fix the file (or supply mlbam_id explicitly); a "
            f"duplicated key would multiply rows in the consensus join."
        )

    unresolved = work[work["mlbam_id"].isna() | work["rank"].isna()]
    report = {
        "source": source_name,
        "rows": int(len(work)),
        "resolved": int(len(resolved)),
        "resolved_rate": round(len(resolved) / max(len(work), 1), 4),
        "by_method": {str(k): int(v) for k, v in
                      resolved["match_method"].value_counts().items()},
        "ambiguous_names_in_universe": len(ambiguous_names),
        "unresolved_rows": unresolved[["rank", "player_name"]].head(50).to_dict("records"),
    }
    return resolved[["mlbam_id", "rank", "match_method"]].rename(
        columns={"rank": f"rank_{source_name}"}), report


# ── The consensus ────────────────────────────────────────────────────────────────────────────

def _tier(rank: float) -> str | None:
    if rank is None or (isinstance(rank, float) and np.isnan(rank)):
        return None
    for bound, label in CONSENSUS_TIERS:
        if rank <= bound:
            return label
    return CONSENSUS_TIERS[-1][1]


def _rank_pctile(rank: pd.Series) -> pd.Series:
    """Rank (1 = best) → percentile 0-100 where 100 = best, among the ranked rows only.

    Percentile space is what the disagreement residuals are fitted in: raw ranks from a 100-long
    list and a 900-long list are not on the same scale, and fitting across them would let the long
    list's tail dominate the slope.
    """
    valid = rank.notna()
    if not valid.any():
        return pd.Series(np.nan, index=rank.index, dtype="float64")
    pct = rank.rank(pct=True, ascending=True, na_option="keep")
    return ((1.0 - pct) * 100.0).astype("float64")


def build_consensus(df: pd.DataFrame, sources: Iterable[RankSource], *, scope: str = "overall",
                    group_col: str | None = None, prefix: str = "consensus") -> pd.DataFrame:
    """Aggregate the ranks of the sources whose `scope` matches, onto `df`. Returns new columns only.

    Adds, for the scope:
      `{prefix}_rank_mean`   mean of the ranks that EXIST (never imputed — module docstring #1)
      `{prefix}_rank`        1..N ordering of those means (within `group_col` if given)
      `{prefix}_pctile`      that ordering as a 0-100 percentile (100 = best)
      `{prefix}_n_sources`   how many sources ranked him ⭐ read this beside every mean
      `{prefix}_sources`     which ones, comma-joined
      `{prefix}_confidence`  'high' (≥3) / 'medium' (2) / 'low (1 source)' — see docstring #2
      `{prefix}_tier`        the tier bucket (overall scope only; an org rank has no tier meaning)
      `{prefix}_rank_spread` max−min of the contributing ranks: how much the sources actually differ
    """
    in_scope = [s for s in sources if s.scope == scope]
    out = pd.DataFrame(index=df.index)
    if not in_scope:
        return out

    missing = [s.rank_col for s in in_scope if s.rank_col not in df.columns]
    if missing:
        raise ConsensusError(
            f"rank column(s) {missing} are absent from the frame — a source that contributes no "
            f"column would silently make the consensus one source narrower than it claims."
        )

    ranks = pd.DataFrame({s.name: pd.to_numeric(df[s.rank_col], errors="coerce")
                          for s in in_scope}, index=df.index)
    out[f"{prefix}_rank_mean"] = ranks.mean(axis=1, skipna=True).round(2)
    out[f"{prefix}_n_sources"] = ranks.notna().sum(axis=1).astype(int)
    # ⚠️ Spread is UNDEFINED for a single source, not zero. `max − min` over one value is 0.0, which
    # renders as "every source agrees exactly" — the precise opposite of what one opinion means, and
    # the most plausible way this column gets misread. NULL where it cannot be measured.
    spread = (ranks.max(axis=1) - ranks.min(axis=1)).round(1)
    out[f"{prefix}_rank_spread"] = spread.where(ranks.notna().sum(axis=1) >= 2)
    out[f"{prefix}_sources"] = [
        ", ".join(sorted(name for name in ranks.columns if pd.notna(row[name])))
        for _, row in ranks.iterrows()
    ]

    mean_col = out[f"{prefix}_rank_mean"]
    if group_col is not None:
        if group_col not in df.columns:
            raise ConsensusError(f"group_col {group_col!r} is not a column of the frame.")
        ordering = mean_col.groupby(df[group_col]).rank(method="min", ascending=True)
        pctile = pd.Series(np.nan, index=df.index, dtype="float64")
        for _, idx in df.groupby(group_col).groups.items():
            pctile.loc[idx] = _rank_pctile(mean_col.loc[idx])
    else:
        ordering = mean_col.rank(method="min", ascending=True)
        pctile = _rank_pctile(mean_col)
    out[f"{prefix}_rank"] = ordering.astype("Int64")
    out[f"{prefix}_pctile"] = pctile.round(1)

    n = out[f"{prefix}_n_sources"]
    out[f"{prefix}_confidence"] = np.select(
        [n >= 3, n == 2, n == 1],
        ["high (3+ sources)", "medium (2 sources)", "low (1 source)"],
        default="none",
    )
    if scope == "overall":
        out[f"{prefix}_tier"] = out[f"{prefix}_rank"].map(_tier)
    return out


def attach_consensus(df: pd.DataFrame, sources: Iterable[RankSource], *,
                     model_score_col: str = "model_score",
                     player_type_col: str | None = "player_type",
                     org_col: str = "org") -> tuple[pd.DataFrame, dict[str, Any]]:
    """The full E7.11 layer: both consensus scopes, per-source disagreement, ours-vs-consensus.

    Everything comparative in here is a RESIDUAL (module docstring #3). The report carries the
    per-source coverage the AC requires.
    """
    sources = list(sources)
    if not sources:
        raise ConsensusError("no ranking sources supplied.")
    names = [s.name for s in sources]
    if len(set(names)) != len(names):
        raise ConsensusError(f"duplicate source name(s) in {names}.")

    out = df.copy()
    overall = build_consensus(out, sources, scope="overall", prefix="consensus")
    org = build_consensus(out, sources, scope="org", group_col=org_col, prefix="org_consensus")
    out = pd.concat([out, overall, org], axis=1)

    # ── per-source disagreement vs the consensus ─────────────────────────────────────────────
    # Fitted in percentile space against the consensus percentile of the SAME scope, and only over
    # rows where BOTH exist. A source is compared to the consensus it is part of — a mild
    # self-comparison, but the alternative (leave-one-out per source) changes the reference frame
    # per column, which makes two sources' disagreement numbers incomparable. Stated, not hidden.
    for source in sources:
        # A scope with no sources produced no columns at all (e.g. a run with no org-ranked
        # source) — that source simply has no consensus to be compared against, which is a
        # coverage fact, not an error.
        prefix = "consensus" if source.scope == "overall" else "org_consensus"
        cons_col, n_col = f"{prefix}_pctile", f"{prefix}_n_sources"
        if cons_col not in out.columns or source.rank_col not in out.columns:
            continue
        src_pct = _rank_pctile_by_scope(out, source, org_col)
        out[f"pctile_{source.name}"] = src_pct.round(1)

        # ⚠️ ONLY MULTI-SOURCE ROWS CAN DISAGREE. Where this source is the only one that ranked a
        # player, the "consensus" IS this source — comparing them measures nothing but the
        # difference between two percentile denominators (the source's own ranked pool vs the
        # consensus pool), which showed up in the first real run as a lopsided 89-vs-35 split of
        # spurious flags. Restricted to n_sources ≥ 2; everyone else is NULL, i.e. "not comparable".
        comparable = (out[n_col] >= 2) & src_pct.notna() & out[cons_col].notna()
        resid = pd.Series(np.nan, index=out.index, dtype="float64")
        if comparable.any():
            resid.loc[comparable] = residual_vs_fit(src_pct[comparable], out.loc[comparable, cons_col])
        out[f"vs_consensus_{source.name}"] = resid
        labels = _label(resid, high=f"{source.label} HIGHER", low=f"{source.label} LOWER")
        out[f"vs_consensus_{source.name}_label"] = labels.where(
            resid.notna(), "n/a (only one source ranked him)")

    # ── OUR line vs the consensus — the differentiated view the story asks for ───────────────
    # Residual of our model score on the consensus percentile, fitted WITHIN player type: the
    # relationship between a scouting consensus and our translated line is genuinely different for
    # bats and arms (that asymmetry is E7.8's whole finding), so one pooled fit smears them.
    out["mle_vs_consensus"] = np.nan
    if model_score_col in out.columns and ("consensus_pctile" in out.columns
                                           or "org_consensus_pctile" in out.columns):
        # Prefer the OVERALL consensus; fall back to the org one for the ~90% of the board no
        # source ranks overall. Falling back is what keeps the differentiated view from being a
        # top-100-only column on a 1,300-player draft board.
        overall_pct = out.get("consensus_pctile", pd.Series(np.nan, index=out.index))
        org_pct = out.get("org_consensus_pctile", pd.Series(np.nan, index=out.index))
        best_pct = overall_pct.where(overall_pct.notna(), org_pct)
        out["consensus_pctile_used"] = best_pct.round(1)
        # ⚠️ THE TWO SCOPES ARE NOT ONE VARIABLE. An overall percentile of 50 means "≈65th best
        # prospect alive"; an org percentile of 50 means "middle of one club's top 30". Pooling
        # them into a single fit would regress our line against an x whose meaning changes
        # mid-column. So the residual is fitted separately per (player type × scope used), and the
        # scope is emitted so a reader can see which reference frame a row was judged in.
        out["consensus_scope_used"] = np.where(
            overall_pct.notna(), "overall", np.where(org_pct.notna(), "org", None))
        types = (out[player_type_col].fillna("_") if player_type_col in out.columns
                 else pd.Series("_", index=out.index))
        for ptype in types.dropna().unique():
            for scope_used in ("overall", "org"):
                mask = ((types == ptype) & (out["consensus_scope_used"] == scope_used)
                        & out[model_score_col].notna() & best_pct.notna())
                if int(mask.sum()) < 3:
                    continue
                out.loc[mask, "mle_vs_consensus"] = residual_vs_fit(
                    out.loc[mask, model_score_col], best_pct.loc[mask])
    out["mle_vs_consensus_label"] = _label(out["mle_vs_consensus"],
                                           high="WE'RE HIGHER than the consensus",
                                           low="CONSENSUS HIGHER than us")
    out.loc[out["mle_vs_consensus"].isna(), "mle_vs_consensus_label"] = "n/a (no MLE / no consensus)"

    return out, consensus_report(out, sources)


def _rank_pctile_by_scope(df: pd.DataFrame, source: RankSource, org_col: str) -> pd.Series:
    """A source's own rank as a percentile — within org for an org-scoped source, else overall."""
    ranks = pd.to_numeric(df[source.rank_col], errors="coerce")
    if source.scope != "org":
        return _rank_pctile(ranks)
    pct = pd.Series(np.nan, index=df.index, dtype="float64")
    for _, idx in df.groupby(org_col).groups.items():
        pct.loc[idx] = _rank_pctile(ranks.loc[idx])
    return pct


def _label(resid: pd.Series, *, high: str, low: str) -> pd.Series:
    return pd.Series(
        np.select([resid >= DISAGREEMENT_THRESHOLD, resid <= -DISAGREEMENT_THRESHOLD],
                  [high, low], default="agree"),
        index=resid.index,
    )


# ── Reporting ────────────────────────────────────────────────────────────────────────────────

def coverage_table(df: pd.DataFrame, sources: Iterable[RankSource]) -> pd.DataFrame:
    """Per-source coverage: how many board players each source ranks, and how deep it goes."""
    rows = []
    total = len(df)
    for source in sources:
        ranks = pd.to_numeric(df.get(source.rank_col, pd.Series(dtype="float64")), errors="coerce")
        ranked = int(ranks.notna().sum())
        rows.append({
            "source": source.name,
            "label": source.label,
            "access": source.access,
            "scope": source.scope,
            "players_ranked": ranked,
            "coverage_of_board": round(ranked / max(total, 1), 4),
            "best_rank": (float(ranks.min()) if ranked else None),
            "deepest_rank": (float(ranks.max()) if ranked else None),
            "note": source.note,
        })
    return pd.DataFrame(rows)


def consensus_report(df: pd.DataFrame, sources: Iterable[RankSource]) -> dict[str, Any]:
    sources = list(sources)
    rep: dict[str, Any] = {
        "universe_rows": int(len(df)),
        "coverage_by_source": coverage_table(df, sources).to_dict("records"),
    }
    for prefix, label in (("consensus", "overall"), ("org_consensus", "org")):
        col = f"{prefix}_n_sources"
        if col not in df.columns:
            continue
        counts = df[col].value_counts().sort_index()
        rep[f"{label}_players_with_consensus"] = int((df[col] > 0).sum())
        rep[f"{label}_players_by_n_sources"] = {int(k): int(v) for k, v in counts.items()}
        rep[f"{label}_multi_source_players"] = int((df[col] >= 2).sum())
    for source in sources:
        col = f"vs_consensus_{source.name}"
        if col in df.columns:
            resid = df[col]
            rep.setdefault("disagreement_counts", {})[source.name] = {
                "higher_than_consensus": int((resid >= DISAGREEMENT_THRESHOLD).sum()),
                "lower_than_consensus": int((resid <= -DISAGREEMENT_THRESHOLD).sum()),
                "comparable": int(resid.notna().sum()),
            }
    if "mle_vs_consensus" in df.columns:
        resid = df["mle_vs_consensus"]
        rep["mle_vs_consensus"] = {
            "comparable": int(resid.notna().sum()),
            "we_are_higher": int((resid >= DISAGREEMENT_THRESHOLD).sum()),
            "consensus_higher": int((resid <= -DISAGREEMENT_THRESHOLD).sum()),
        }
    return rep


def format_consensus_report(rep: dict[str, Any], extra: Iterable[str] = ()) -> str:
    lines = ["", "──────── E7.11 MULTI-SOURCE CONSENSUS — COVERAGE REPORT ────────",
             f"  universe (board ∪ ranked players) : {rep.get('universe_rows', 0):,}", "",
             "  PER-SOURCE COVERAGE",
             f"    {'source':<22}{'access':<10}{'scope':<9}{'ranked':>8}  {'of universe':>11}  depth"]
    for row in rep.get("coverage_by_source", []):
        depth = (f"1–{int(row['deepest_rank'])}" if row.get("deepest_rank") else "—")
        lines.append(f"    {row['label']:<22}{row['access']:<10}{row['scope']:<9}"
                     f"{row['players_ranked']:>8}  {row['coverage_of_board']:>10.1%}  {depth}")
    for scope in ("overall", "org"):
        key = f"{scope}_players_by_n_sources"
        if key not in rep:
            continue
        lines += ["", f"  {scope.upper()} CONSENSUS — players by number of sources ranking them",
                  f"    {rep[key]}   "
                  f"(≥2 sources: {rep.get(f'{scope}_multi_source_players', 0):,})"]
    if rep.get("disagreement_counts"):
        lines += ["", "  DISAGREEMENT vs CONSENSUS (a RESIDUAL, not a raw gap — see the module doc)"]
        for name, counts in rep["disagreement_counts"].items():
            lines.append(f"    {name:<22} higher {counts['higher_than_consensus']:>4}   "
                         f"lower {counts['lower_than_consensus']:>4}   "
                         f"(of {counts['comparable']:,} comparable)")
    if rep.get("mle_vs_consensus"):
        m = rep["mle_vs_consensus"]
        lines += ["", "  ⭐ OUR MLE LINE vs THE CONSENSUS (the differentiated view)",
                  f"    comparable {m['comparable']:,}   we're higher {m['we_are_higher']:,}   "
                  f"consensus higher {m['consensus_higher']:,}"]
    lines += ["", "  🔒 best_alpha = 0. A consensus is a DESCRIPTION, not a claim to beat any",
              "     source. Nothing here was tested for accuracy against realized outcomes."]
    lines += list(extra)
    lines.append("────────────────────────────────────────────────────────────────")
    return "\n".join(lines)
