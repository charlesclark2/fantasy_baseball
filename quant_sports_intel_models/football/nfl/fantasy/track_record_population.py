"""track_record_population.py — NF-D17: THE PRE-REGISTRATION for the track-record Δρ
population-sensitivity re-computation.

⚠️⚠️ THIS FILE IS THE PRE-REGISTRATION AND IS COMMITTED **BEFORE** ANY NUMBER IS COMPUTED.
Nothing below may be edited once the harness (`run_nf_d17_population_sensitivity.py`) has been run
against real data — a population rule, a source set, a metric or a decision rule changed after seeing
a result is the E2.1-r inversion (CLAUDE.md 📏) pointed at our own marketing, which is the single
failure mode this story exists to avoid. If a rule turns out to be wrong, the honest move is to
DISCLOSE it in the memo beside the pre-registered reading, never to silently re-write it here.

═══════════════════════════════════════════════════════════════════════════════════════════════
§1 — THE QUESTION
═══════════════════════════════════════════════════════════════════════════════════════════════
NF3.2 shipped a PUBLIC receipts page whose headline is built verbatim from the NF-D3 scorecard's
`aggregate.adp` numbers:

    "On average across 6 past seasons (2019–2024), our within-position ordering correlation vs
     realized outcomes is 0.517, against ADP's 0.494 (Δρ +0.022)."

`adp` there is Fantasy Football Calculator (FFC) — ONE of two registered real-draft ADP sources.
NF3.2 flagged, and the operator DEFERRED, a population-sensitivity observation: on a "matched
population" the same comparison reportedly reads ≈ **+0.144** vs FFC and ≈ **+0.088** vs MFL. If that
holds, the shipped, already-honest claim is materially UNDERSTATED.

⭐ ONE THING MUST BE SAID FIRST, BECAUSE IT CHANGES WHAT THIS STORY IS. The shipped +0.022 is NOT an
unmatched us-vs-them comparison. `benchmark_scorecard.build_scorecard` already scores BOTH sides on
`base ∩ system` (`m = base.merge(s, how="inner")`, then `_score_pair(m, ...)` grades our column and
the system's column on that identical frame). So the E7.8 / NF-D13 benchmark-population defect —
comparing our ρ over one player set against theirs over a different one — is ALREADY absent. What is
NOT controlled is the population's DEPTH and COMPOSITION *between sources*: FFC's aligned universe is
~140–172 players/season (31–40% of our scored universe) while MFL's is ~251–286 (54–67%). Δρ is not a
population-free quantity, so "FFC-only" is an implicit population choice, and that choice is what this
story measures.

⇒ THE PRE-REGISTERED QUESTION: **how does Δρ vs a real-draft ADP source move as the evaluation
population changes, is the shipped FFC-only population a CONSERVATIVE choice, and by how much —
with honest uncertainty?**

═══════════════════════════════════════════════════════════════════════════════════════════════
§2 — THE METRIC (FIXED; DELIBERATELY UNCHANGED FROM THE SHIPPED ONE)
═══════════════════════════════════════════════════════════════════════════════════════════════
Within-position Spearman ρ(score, `real_fp_ppr`) over (QB, RB, WR, TE); a position enters only with
≥10 rows and non-degenerate variance (`benchmark_scorecard._spearman`); "pooled" = the unweighted
arithmetic mean over the positions that entered; Δρ = ρ_us − ρ_source; the reported figure is the
unweighted mean of the per-season Δρ (exactly `benchmark_scorecard._aggregate`).

⛔ THE METRIC IS NOT RE-CHOSEN. This story changes the POPULATION and nothing else — moving both at
once makes every difference uninterpretable. The harness calls `benchmark_scorecard._score_pair`
VERBATIM rather than re-implementing it (the NF1.5b "never re-derive the join" rule), so a per-
population number can never disagree with the shipped scorecard for a reason other than population.

═══════════════════════════════════════════════════════════════════════════════════════════════
§3 — THE POPULATIONS (FIXED, EXHAUSTIVE, ALL REPORTED)
═══════════════════════════════════════════════════════════════════════════════════════════════
For a season y, with `U` = our shipped NF1.5 projection ∩ realized(g ≥ 6) ∩ {QB,RB,WR,TE} (the
scorecard's `base`), `F` = FFC-ranked players (post-crosswalk), `M` = MFL-ranked players:

  P0  SHIPPED / PER-SOURCE PAIRWISE ...... `U ∩ S`, each source S scored on its own aligned set.
      This IS the shipped number and is the reference every other row is read against.

  P1  CROSS-SOURCE MATCHED (PRIMARY) ..... `U ∩ F ∩ M`. Both real-draft ADP sources scored on the
      IDENTICAL player set, so "FFC's Δ vs MFL's Δ" is like-for-like and neither carries its own
      population. Seasons: those where BOTH sources exist (FFC has no 2025 archive at all, confirmed
      live — so P1 is 2019–2024 by construction, not by selection).

  P2  DEPTH CURVE (ATTRIBUTION) .......... within `U ∩ S`, the top-K players for
      K ∈ (100, 150, 200, 250, 300, ALL). Measures Δρ as a function of draft depth directly — the
      mechanism behind any P0↔P1 difference.
      ⚠️ PRE-REGISTERED TWO-SIDEDNESS, AND IT IS LOAD-BEARING: truncating to "the top K" by ONE
      side's own ordering RANGE-RESTRICTS that side and therefore ATTENUATES its ρ, biasing Δρ toward
      the other side. So P2 is computed BOTH ways — top-K by the SOURCE's ordering (biased toward US)
      and top-K by OUR ordering (biased toward THEM) — and ONLY THE BAND BETWEEN THEM is
      interpretable. A one-sided depth reading is inadmissible as evidence and must never be quoted.
      ⛔ NO K IS EVER SELECTED. The deliverable is the curve; picking the K that reads best is the
      inversion this story exists to prevent.

  P3  COVERAGE DIAGNOSTIC ................ not a Δρ population: |U ∩ S| / |U| per source per season,
      reported so every Δρ in the memo carries the population that produced it (the story's "report
      each population's n" requirement, and the NF1.8 "state the margin in ROWS" discipline).

⛔ NO OTHER POPULATION MAY BE ADDED AFTER THE FACT. If the run suggests one, it is recorded as a
follow-up hypothesis in the memo, never computed into this story's reported set.

═══════════════════════════════════════════════════════════════════════════════════════════════
§4 — THE SOURCE SET (FIXED)
═══════════════════════════════════════════════════════════════════════════════════════════════
HEADLINE-ELIGIBLE (the public claim is about a real-draft ADP consensus): `adp` (FFC) and `mfl_adp`
(MyFantasyLeague) — and ONLY these two.
CONTEXT, REPORTED, NEVER HEADLINE-ELIGIBLE: `ecr` (FantasyPros), `sleeper`, `espn`. The shipped page's
honest framing already names that these out-order us; they are carried so the memo cannot be accused
of reporting only the sources that flatter us, but they can never become a headline.
⛔ CHERRY-PICKING THE SOURCE IS EXACTLY AS INADMISSIBLE AS CHERRY-PICKING THE POPULATION.

═══════════════════════════════════════════════════════════════════════════════════════════════
§5 — ANCHORS AND CONTROLS (ALL FOUR MUST PASS OR THE ENTIRE READING IS VOID)
═══════════════════════════════════════════════════════════════════════════════════════════════
Because a population change can silently invert a comparison, every population is scored with the
same anchor set (CLAUDE.md 📏 / NF1.7 (a): a check that cannot fail is not a check, and an anchor that
fails to evaluate must RAISE, never pass vacuously):

  A1  IDENTITY .......... score a source AGAINST ITSELF as "us". Δρ must be EXACTLY 0.0 on every
      population. Proves the population machinery is symmetric and cannot manufacture a gap.
  A2  ORACLE FLOOR ...... `real_fp_ppr` itself as our score. Must post the MAXIMUM Δρ on every
      population, and no real arm may beat it. Same-family/same-sample by construction (identical
      frame, identical metric) — the NF1.7 (b) / NF1.9 (f) matched-n requirement is satisfied by
      scoring it on the very frame under test, not on a re-fit.
  A3  DEGENERATE CEILING  a seeded RANDOM ordering as our score. Must be strongly NEGATIVE on every
      population and must never beat the real arm. This is the NF1.8 rule in its second job: a
      population on which a coin-flip "beats" ADP is a population that has broken the metric.
  A4  REPRODUCTION ...... P0 must reproduce the SHIPPED scorecard's own
      `aggregate.adp.delta_rho_pooled = +0.022` and `aggregate.mfl_adp.delta_rho_pooled = +0.173`
      to the precision the scorecard prints. If it does not, the harness is wrong and NO other number
      in the run is trustworthy — the run HALTS rather than reporting.

═══════════════════════════════════════════════════════════════════════════════════════════════
§6 — UNCERTAINTY (NO FAKED PRECISION)
═══════════════════════════════════════════════════════════════════════════════════════════════
Every reported Δρ carries: (a) n_seasons and the across-season SD of the per-season Δρ; (b) the
population n per season; (c) a PAIRED player-level bootstrap — resample players WITH REPLACEMENT
within (season, position), recompute BOTH sides on the SAME resample, re-pool, 1000 seeded draws → a
90% interval on the season-averaged Δρ. Pairing is mandatory: an unpaired interval would measure the
two sides' independent noise instead of the noise in their DIFFERENCE, and would be far too wide.

DECISION RULE ON UNCERTAINTY, FIXED IN ADVANCE: two populations' Δρ are called MATERIALLY DIFFERENT
only if their 90% bootstrap intervals DO NOT OVERLAP. Otherwise the memo says INDISTINGUISHABLE.
A Δρ is called POSITIVE only if its own 90% interval excludes 0.

═══════════════════════════════════════════════════════════════════════════════════════════════
§7 — THE FORENSIC LEG (also pre-registered, so it cannot be quietly dropped)
═══════════════════════════════════════════════════════════════════════════════════════════════
The deferred figures (+0.144 vs FFC, +0.088 vs MFL) have NO recorded derivation in the repo — NF3.2
carded the observation, not the code that produced it. The harness therefore ALSO reports which, if
any, of the pre-registered populations lands near them.

⚠️ PRE-COMMITMENT: **if no pre-registered population reproduces ≈ +0.144, that is a REPORTED FINDING,
not an omission.** The memo must say plainly that the deferred figure was not reproduced under any
pre-registered definition, and must NOT go hunting for a definition that produces it — reverse-
engineering a population to hit a remembered number is the same inversion as reverse-engineering it to
hit a flattering one, and is strictly worse because the target is already known.

═══════════════════════════════════════════════════════════════════════════════════════════════
§8 — DECISION RULE (FIXED IN ADVANCE; THE SESSION DOES NOT GET TO PICK A HEADLINE)
═══════════════════════════════════════════════════════════════════════════════════════════════
1. The shipped +0.022 STAYS LIVE from this session regardless of the outcome. It is the NF-D13-audited
   correct FFC-only Δρ and is not in question. Nothing here silently edits a public claim.
2. The memo reports EVERY population × EVERY source with n, SD and interval — all of it, labelled.
3. This session recommends AT MOST ONE alternative framing, and only the PRE-REGISTERED PRIMARY (P1,
   the cross-source matched population), and only if ALL of: (i) all four anchors pass; (ii) P1's Δρ
   90% interval excludes 0; (iii) P1 is MATERIALLY different from P0 under §6's non-overlap rule.
   If any of those fails the recommendation is "KEEP THE SHIPPED NUMBER" — a bigger point estimate is
   NOT a reason to change a public claim.
4. Even when all three hold, the change is the OPERATOR's decision and a DISCLOSED product change
   (re-export + changelog), never a quiet edit. `best_alpha = 0`: this is a descriptive-accuracy
   question and no bet or edge claim rides on it.
5. ⭐ A ONE-DIRECTION-ONLY RESULT IS STILL A RESULT. This story can only make an already-honest claim
   MORE favourable or leave it alone; it can never be used to argue the shipped number was too high.
   If the measurement pointed the other way, that would be a defect report, not a marketing input.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── §3 populations ─────────────────────────────────────────────────────────────────────────────
POPULATIONS = ("P0_shipped", "P1_cross_source_matched", "P2_depth_curve")

# §3 P2 — the pre-registered depth grid. `None` = the untruncated aligned universe (= P0).
DEPTH_GRID: tuple[int | None, ...] = (100, 150, 200, 250, 300, None)

# §3 P2 — the two truncation orderings. BOTH are always computed; only the band between them is
# interpretable (see §3). Keys are the column whose descending order defines "the top K".
DEPTH_TRUNCATION_SIDES = ("by_source", "by_us")

# ── §4 source set ──────────────────────────────────────────────────────────────────────────────
HEADLINE_ELIGIBLE_SOURCES = ("adp", "mfl_adp")
CONTEXT_SOURCES = ("ecr", "sleeper", "espn")

# ── §5 anchors ─────────────────────────────────────────────────────────────────────────────────
ANCHORS = ("A1_identity", "A2_oracle_floor", "A3_degenerate_random", "A4_reproduction")

# §5 A4 — the SHIPPED figures this run must reproduce before any other number is trusted. Taken from
# `ablation_results/nf_d3_benchmark_scorecard_nf1_5.json` (the exact artifact the live public headline
# was built from) and hard-coded here so the reproduction check cannot drift with a re-generated file.
# ⭐ The pin MOVES ONLY WHEN THE HEADLINE'S ARTIFACT IS DELIBERATELY REGENERATED, in the SAME change
# as that artifact — never to fit a result. History (kept so a reader can see what each vintage
# reproduced):
#   2026-08-03 (NF-D17 registration): adp +0.022 / 6 seasons (2025 ADP not yet archived); mfl +0.173 / 7
#   2026-08-15 (NF-TR2b track-record refresh): the 2019–2025 boards rebuilt under the served veteran
#              LEVEL recalibration (walk-forward, `veteran_level_policy`) + 2025 ADP now archived →
#              adp +0.018 / 7; mfl +0.169 / 7 (per-position Δρ within ±0.01 of the prior vintage —
#              a positive per-position constant cannot re-order a position; the pooled move is the
#              cross-position re-ranking + the added 2025 season).
SHIPPED_DELTA_RHO = {"adp": 0.018, "mfl_adp": 0.169}
SHIPPED_N_SEASONS = {"adp": 7, "mfl_adp": 7}
REPRODUCTION_TOLERANCE = 0.001  # the precision the scorecard itself prints

# ── §6 uncertainty ─────────────────────────────────────────────────────────────────────────────
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 20260803
BOOTSTRAP_INTERVAL = 0.90

# ── §7 forensic leg ────────────────────────────────────────────────────────────────────────────
# The DEFERRED NF3.2 figures this run tries to place. Recorded so the memo cannot quietly drop them.
DEFERRED_NF3_2_FIGURES = {"adp": 0.144, "mfl_adp": 0.088}
# "near" for the purposes of §7's placement report only — never a gate, never a target.
FORENSIC_MATCH_TOLERANCE = 0.02


@dataclass(frozen=True)
class PopulationSpec:
    """One pre-registered evaluation population (§3)."""

    key: str
    label: str
    # sources that must ALL rank a player for him to enter (beyond `U`); empty = the source under test
    # only (P0's per-source pairwise rule).
    require_sources: tuple[str, ...]
    depth: int | None = None
    truncate_by: str | None = None

    def describe(self) -> str:
        bits = [self.label]
        if self.require_sources:
            bits.append(f"require={'+'.join(self.require_sources)}")
        if self.depth is not None:
            bits.append(f"top{self.depth}[{self.truncate_by}]")
        return " · ".join(bits)


def preregistered_specs() -> list[PopulationSpec]:
    """Every population this story is allowed to report, in a fixed order. Adding to this list after
    a run is a pre-registration violation (§3)."""
    specs = [
        PopulationSpec("P0_shipped", "P0 shipped (per-source pairwise)", ()),
        PopulationSpec(
            "P1_cross_source_matched", "P1 cross-source matched", HEADLINE_ELIGIBLE_SOURCES,
        ),
    ]
    for side in DEPTH_TRUNCATION_SIDES:
        for k in DEPTH_GRID:
            if k is None:
                continue  # K=ALL is P0 by construction; reported there, never duplicated here
            specs.append(
                PopulationSpec(f"P2_depth{k}_{side}", "P2 depth curve", (), depth=k, truncate_by=side)
            )
    return specs
