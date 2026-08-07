// NF-TR1 — THE CANONICAL FANTASY CLAIM COPY. One home for every claim-bearing string the fantasy
// product renders, so a surface cannot quietly write its own stronger version.
//
// ══ WHAT LIVES HERE AND WHAT DOES NOT ══════════════════════════════════════════════════════════
//
// HERE: the CALIBRATION HOOK — what the product *is*. It carries no measured figure, so it is not
// a claim about model performance and does not belong in the export.
//
// ⛔ NOT HERE: anything with a NUMBER in it. Every measured figure (the gap, the interval, the
// player count, the per-position split) is read from the served artifact's `claim` block, built by
// `export_track_record_json.build_claim` from the NF-D3 scorecard and the NF-D17 population
// artifact. That is the E9.56b/NF-D3 discipline: a figure typed into a component cannot be
// reconciled against the measurement it came from, and drifts silently the first time the model is
// re-scored. If you find yourself adding a number to this file, it belongs in the exporter.
//
// ══ WHY IT IS A MODULE AND NOT INLINE JSX ══════════════════════════════════════════════════════
//
// E9.46 (home hero) quotes the same claim, /subscribe quotes it, the locked-surface upgrade banner
// quotes it. NF-TR1 runs first precisely so those can reuse this wording VERBATIM instead of each
// paraphrasing it — and paraphrase is how a hedge gets dropped. `betting_ml/tests/
// test_nf_tr1_claim_copy.py` parses THIS FILE'S string literals and runs the export's
// `_CLAIM_DENYLIST` plus the governance gate over them, so the screening covers the frontend copy
// and not only the generated copy.

/** The primary hook, in the order NF-TR1 requires it be read: what you get, before any comparison.
 *
 *  ⭐ CALIBRATION LEADS. The benchmark comparison is the SECONDARY claim and is rendered after this
 *  block on every surface. That ordering is an acceptance criterion, not a layout preference:
 *  leading with "we did better than ADP" makes a small, interval-straddling gap the product's
 *  headline promise, which is the exact overclaim the honest-analytics rule forbids. */
export const CALIBRATION_HOOK: readonly { title: string; detail: string }[] = [
  {
    title: "Honest projected points",
    detail:
      "A full-season point projection for every player — built to be right on average, not to look bold.",
  },
  {
    title: "A range, so you know how sure we are",
    detail:
      "Every projection ships with an 80% range. A wide range means we genuinely do not know, and we say so.",
  },
  {
    title: "Your league's scoring",
    detail:
      "Half-PPR, full-PPR, superflex, custom bonuses — the numbers are recomputed for your settings, not converted from someone else's.",
  },
  {
    title: "We show our inputs",
    detail:
      "The drivers behind a projection are on the page. You can disagree with us and see exactly where.",
  },
]

/** The section heading the secondary (benchmark) claim renders under, used identically on every
 *  surface so the comparison always arrives labelled as the *secondary* thing it is. */
export const TRACK_RECORD_HEADING = "How it has actually done"

/** The label for the precise/methodology layer. The exact approved sentence, the named benchmark,
 *  the metric, the player count, the seasons and the interval live BEHIND this — relocated below
 *  the plain lead, never deleted. */
export const METHOD_DISCLOSURE_LABEL = "How we measured this"

/** Shown when the served artifact predates NF-TR1 and carries no `claim` block.
 *
 *  ⚠️ THE DEPLOY-SKEW WINDOW IS REAL AND IT IS ASYMMETRIC. `frontend/` auto-deploys on merge while
 *  the artifact only gains its `claim` block when the operator re-runs the exporter with
 *  `--publish` (NF-C0's rule, one layer over: here the skew is frontend-vs-ARTIFACT rather than
 *  frontend-vs-Lambda). In that window this component must NOT promote the legacy `headline` into
 *  the lead position — the legacy wording asserts "we finished ahead" with no interval beside it,
 *  which is precisely the un-hedged form NF-TR1 exists to retire. So the legacy string is rendered
 *  inside the methodology layer with this note, and the calibration hook above still leads. */
export const LEGACY_CLAIM_NOTE =
  "This is the previous wording of our track-record summary. The fuller breakdown — the benchmark, the sample size and the uncertainty range — publishes with the next export."

/** The standing caveat about what the served board actually is, for a surface that renders the
 *  claim WITHOUT the artifact (E9.46's static hero). Mirrors `build_claim`'s `architecture` note;
 *  when the artifact IS available, prefer `claim.architecture` so there is one string, not two. */
export const ARCHITECTURE_CAVEAT =
  "Our projected points come from a model that never looks at the draft market. A second model sets the order players are ranked in, and at most positions that order blends the market's own consensus with ours — so our ranking is not an independent read on the market."
