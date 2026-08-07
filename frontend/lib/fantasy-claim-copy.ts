// NF-TR1 — THE CANONICAL FANTASY COPY. One home for every claim-bearing string the fantasy product
// renders, so a surface cannot quietly write its own stronger version.
//
// ══ THE SPLIT THIS FILE ENCODES (operator 2026-08-07, GROWTH-100) ══════════════════════════════
//
// The track record is a TRUST LINK, not the sell. Two different jobs, two different registers, and
// putting either one's copy on the other's surface is the failure this module exists to prevent:
//
//   MARKETING surfaces (home hero, /subscribe, the locked-board upgrade banner)
//     → lead with the PRODUCT: rankings built for YOUR league's scoring, honest ranges,
//       transparent inputs, and the decision support that is the paid half. They LINK to the track
//       record; ⛔ they never QUOTE its number, and they never lead or close on a hedge. A
//       skeptical visitor is one click from the whole measurement — a marketing block that recites
//       a small, interval-straddling statistic converts nobody and informs nobody.
//
//   THE TRACK RECORD PAGE
//     → the rigorous destination a curious or skeptical visitor OPTS INTO. Every hedge lives
//       there, where it builds trust instead of repelling: the interval that includes zero, the
//       running-back wash, the year-to-year swing. That copy is GENERATED, not written here — see
//       `export_track_record_json.build_claim`.
//
// ⛔ NOT HERE: anything with a MEASURED NUMBER in it. Every figure (the gap, the interval, the
// player count, the per-position split) is read from the served artifact's `claim` block. That is
// the E9.56b/NF-D3 discipline: a figure typed into a component cannot be reconciled against the
// measurement it came from, and drifts silently the first time the model is re-scored. If you find
// yourself adding a number to this file, it belongs in the exporter.
//
// ══ WHY IT IS A MODULE AND NOT INLINE JSX ══════════════════════════════════════════════════════
//
// E9.46's home hero, /subscribe and the upgrade banner all need the same wedge and the same trust
// link. NF-TR1 runs first precisely so those reuse this wording VERBATIM instead of each
// paraphrasing it — paraphrase is how a hedge gets dropped on one surface and a boast appears on
// another. `betting_ml/tests/test_nf_tr1_claim_copy.py` parses THIS FILE'S string literals and
// runs the export's `_CLAIM_DENYLIST` plus the governance gate over them, so the screening covers
// the frontend copy and not only the generated copy.

/** The acquisition wedge, in the order it should be read. What the product IS — no comparison to
 *  anyone, no measured figure, nothing to reconcile against a scorecard.
 *
 *  ⭐ TWO SURFACES, ONE SET. On a MARKETING surface this is the pitch. On the Track Record page it
 *  is the calibration block that must render BEFORE any benchmark comparison (an acceptance
 *  criterion, not a layout preference — leading with the comparison makes a gap whose interval
 *  includes zero the product's headline promise). Keeping it as one constant is what stops those
 *  two renders from drifting into two different promises. */
export const PRODUCT_HOOK: readonly { title: string; detail: string }[] = [
  {
    title: "Built for your league, not a generic one",
    detail:
      "Half-PPR, full-PPR, superflex, custom bonuses — every projection and ranking is recomputed for your settings, not converted from someone else's.",
  },
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
    title: "We show our inputs",
    detail:
      "The drivers behind a projection are on the page. You can disagree with us and see exactly where.",
  },
]

/** The free/paid line, stated as a division of labour rather than as a withheld feature.
 *
 *  ⛔ Do not rewrite this into a performance promise. The paid half is DECISION SUPPORT — it does
 *  not claim a better outcome, it claims to do more of the work. */
export const DECISION_SUPPORT_LINE =
  "Free tells you what Credence thinks. A membership helps you decide — draft board, trade and waiver calls, and start/sit, all in your league's scoring."

/** The TRUST LINK. This — not a statistic — is what a marketing surface points at.
 *
 *  ⭐ E9.46's home hero inherits THIS, not a claim: its own headline is the product wedge above.
 *  `blurb` is deliberately an invitation to read the record, never a summary of what the record
 *  says; the moment a marketing surface summarises the finding it has quoted the stat. */
export const TRACK_RECORD_TRUST_LINK = {
  href: "/fantasy/track-record",
  label: "See the track record",
  blurb:
    "Every season since 2019, graded against what actually happened — one row per player, wins and losses both. Free, no account needed.",
} as const

/** ⭐ ADP AS CONTENT, NOT AS A BOAST. The interesting thing about the draft-market comparison is
 *  WHERE we disagree with the crowd and why — that is a reason to click. "We beat consensus" is a
 *  claim, and a small one whose interval includes zero; this is a hook, and it is true regardless
 *  of which side of the gap we are on. Use this wherever a marketing surface wants to reference
 *  consensus at all. */
export const DISAGREEMENT_HOOK =
  "See the players we rank furthest from where the crowd is drafting them — and what is driving the gap."

/** The label for the precise/methodology layer on the Track Record page. The exact approved
 *  sentence, the named benchmark, the metric, the player count, the seasons and the interval live
 *  BEHIND this — relocated below the plain lead, never deleted. */
export const METHOD_DISCLOSURE_LABEL = "How we measured this"

/** Shown on the Track Record page when the served artifact predates NF-TR1 and carries no `claim`.
 *
 *  ⚠️ THE DEPLOY-SKEW WINDOW IS REAL AND IT IS ASYMMETRIC. `frontend/` auto-deploys on merge while
 *  the artifact only gains its `claim` block when the operator re-runs the exporter with
 *  `--publish` (NF-C0's rule, one layer over: here the skew is frontend-vs-ARTIFACT rather than
 *  frontend-vs-Lambda). In that window the page must NOT promote the legacy `headline` into the
 *  lead — the legacy wording asserts "we finished ahead" with no interval beside it, which is
 *  precisely the un-hedged form NF-TR1 exists to retire. So the legacy string renders inside the
 *  methodology layer with this note, and the product hook above still leads. */
export const LEGACY_CLAIM_NOTE =
  "This is the previous wording of our track-record summary. The fuller breakdown — the benchmark, the sample size and the uncertainty range — publishes with the next export."

/** The standing statement of what the served board actually is, for a surface that renders without
 *  the artifact. Mirrors `build_claim`'s `architecture` note; when the artifact IS available,
 *  prefer `claim.architecture` so there is one string, not two. */
export const ARCHITECTURE_CAVEAT =
  "Our projected points come from a model that never looks at the draft market. A second model sets the order players are ranked in, and at most positions that order blends the market's own consensus with ours — so our ranking is not an independent read on the market."
