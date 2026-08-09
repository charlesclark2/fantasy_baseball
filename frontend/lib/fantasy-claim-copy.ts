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
    title: "Points that price in missed games",
    detail:
      "A full-season point projection that already accounts for the chance a player misses time — built to be right on average, not to look bold.",
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

// ══ EXPECTED POINTS — the label that turns a shock into a disclosure ═══════════════════════════
//
// THE PROBLEM IT SOLVES (NF-TR1 surfaced it on the public track record): our published point total
// is an EXPECTED season total — the chance a player misses games is multiplied through it — so it
// sits structurally BELOW the "if he plays every week" numbers most sites publish, and below what a
// player who stayed healthy actually finished on. Unlabelled, that reads as a broken model. It is
// not: it is the honest number, and the fix is to SAY SO next to it.
//
// ⭐ THE FRAMING RULE, and it is the whole point of putting these strings here rather than inline:
// this is a DISCLOSURE, not an apology. The copy states what the number is and why we prefer it,
// and never asks to be forgiven for it. A surface that softens this into "sorry our numbers look
// low" gives away the trust the disclosure is supposed to earn.
//
// ⛔⛔ AND IT MAY NEVER CLAIM AVAILABILITY EXPLAINS THE WHOLE GAP. It does not. Availability carries
// most of the measured level shift, but a residual remains at the worst position, and that residual
// is a real miscalibration with its own carded model story — NOT something a label may absorb. Any
// wording implying "the games column accounts for the difference" would be using an honest
// mechanism to bury a dishonest amount. `EXPECTED_POINTS_NOTE` says so in as many words, and
// `betting_ml/tests/test_expected_points_label_copy.py` holds that clause with its own fixture.
//
// ⛔ NO MEASURED FIGURE, same rule as the rest of this file: no per-position ratio, no games
// average, no bias number. The projected-games VALUE is read per-player from the served artifact
// and rendered beside the points — that is the honest way to show the size of the discount, and it
// cannot drift the way a typed figure would.

/** The column label wherever a projected-points number is shown. One constant so the boards, the
 *  track record and the player page cannot end up calling the same number three things. */
export const EXPECTED_POINTS_LABEL = "Expected pts"

/** The tappable definition behind that label. Rendered through `InfoTip` (a Radix Popover, so it
 *  opens on TAP — the E9.63/NF3 touch lesson: a hover-only tooltip is unreachable on a phone, and
 *  this definition is the whole remedy). */
export const EXPECTED_POINTS_DEFINITION =
  "What we expect this player to score across the whole season, with the chance he misses games already priced in. Most published projections are “if he plays every week” numbers; ours multiplies through by the games we actually expect him to play, so ours is deliberately lower — and lower by more at the positions that lose the most time to injury. Read it next to the projected games and the 80% range: the range is where the stays-healthy, everything-breaks-right seasons live."

/** The projected-games column — what makes the lower points number legible. */
export const PROJECTED_GAMES_LABEL = "Proj. games"

export const PROJECTED_GAMES_DEFINITION =
  "How many of the season's games we expect this player to be available for, out of a full slate of seventeen. It is an average across everything that could happen to him, not a prediction that he misses exactly that many weeks — which is why it is rarely a whole number. This is the figure the points column is scaled by, so it is the quickest way to see how much of a player's projection is an availability discount."

/** The page-level framing on the track record, where a reader meets our points column beside a
 *  finished season's real total and needs to know why one runs under the other.
 *
 *  ⛔ The last sentence is load-bearing and is NOT decoration: availability is the largest part of
 *  the gap and it is not all of it, and a page that let the reader infer otherwise would be worse
 *  than one that never explained anything. Do not trim it for length. */
export const EXPECTED_POINTS_NOTE = {
  title: "Why our points column runs below the finished season",
  detail:
    "The points we publish are an expected season total: the chance a player misses games is already priced into the number. That puts ours below the “if he plays every week” projections most sites show, and below what a player who stayed healthy actually finished on — by design, not by accident. The projected-games column shows how much of that discount is availability for each player. It is not the only reason a projection lands under a finished season, and we do not present it as one.",
} as const

// ══ THE FULL-SEASON RATE — the second reading of the same number ═══════════════════════════════
//
// `EXPECTED_POINTS_LABEL` above is the availability-weighted season total: the chance a player
// misses games is already multiplied through it. That is the honest number and it stays the
// headline. But it answers only one of the two questions a drafter actually has, and the other one
// — "what is he worth in the weeks he plays?" — is the one that makes two players comparable when
// their injury risks differ.
//
// So this is `expected_pts × 17 ÷ expected_games`: the same projection, re-expressed as a
// full-slate rate. NO NEW MODEL RUN, no re-fit — both inputs are already in the served payload, and
// dividing one by the other is arithmetic on numbers the page already shows.
//
// ⛔⛔ DISPLAY ONLY, AND THIS IS A HARD BOUNDARY, NOT A STYLE NOTE. It must never feed VOR, the
// board ordering, tiering, or the optimizer. Ranking on a full-slate rate would rank players as if
// availability did not exist — it would systematically promote exactly the players our projection
// discounts on purpose — and because it re-orders the board it would land on the whole-board
// placement gate (NF-D18/NF-D20's `CONSTRAINT_REFUSED`), which is a model decision with its own
// pre-registration, not a display change. `test_freemium_tier.py` asserts the helper is absent from
// every scoring/ordering module.
//
// ⛔ AND IT IS NOT A CONSENSUS-CALIBRATED NUMBER. It is our own projection divided by our own
// expected games — it is NOT reconciled against anyone else's published "if he plays every week"
// figure, and it is still conservative at running back, where the residual miscalibration
// `EXPECTED_POINTS_NOTE` refuses to bury has not gone anywhere. The copy below says both.

/** The column/tile label for the full-slate reading. "Rate" rather than "if healthy" deliberately:
 *  "if healthy" reads as a PREDICTION about a specific player staying healthy, which is precisely
 *  what this number does not claim. */
export const FULL_SEASON_RATE_LABEL = "Full-season rate"

/** The tappable definition behind that label (rendered through `InfoTip`, so it opens on TAP — the
 *  E9.63/NF3 touch lesson). */
export const FULL_SEASON_RATE_DEFINITION =
  "The same projection, stretched back out to a full seventeen games: expected points divided by expected games. It answers “what is he worth in the weeks he plays?”, which is the fairer way to compare two players whose injury risk differs. It is not a prediction that he plays all seventeen — the expected-points column beside it is the number that prices that in, and it is the one our rankings are built on. It is also our own arithmetic, not a figure reconciled against anyone else's published projections, and it stays conservative at running back."

/** Shown where a full-season rate cannot be computed — no expected-games figure, or zero. An
 *  em-dash with this behind it, never a blank and never a divide-by-zero. */
export const FULL_SEASON_RATE_UNAVAILABLE =
  "We don't publish an expected-games figure for this player, so there is nothing to divide by."

// ══ THE FREE / PAID BOUNDARY — stated as a division of labour, never as a withheld feature ══════
//
// ⭐ THE PRODUCT POINT THIS COPY HAS TO CARRY (GROWTH-100 §1): the paid aha is "what changed
// because it is MY league", and a visitor cannot want that until they have seen the generic board
// and understood that it is generic. So this block only ever appears BESIDE a fully-visible free
// board — it says what the free thing is, then what a membership adds. It is not a lock, there is
// nothing behind it on this page, and it must never be written as though there were.
//
// ⛔ NO PERFORMANCE PROMISE. Not "win your league", not "beat your leaguemates", not "beat ADP".
// The paid half does more of the WORK; it does not claim a better outcome. `best_alpha = 0`.

/** The free half, said plainly so the free surfaces are understood as complete rather than as a
 *  sample.
 *
 *  ⚠️ IT MUST NOT NAME A FORMAT, and that is a correctness constraint rather than a style one. This
 *  block renders on Projections (format-INDEPENDENT — one projection, no scoring applied) as well as
 *  on the scored surfaces, so a sentence about full-PPR at twelve teams would be false on one of the
 *  two pages that shows it. The format scope belongs to the controls it constrains:
 *  `FORMAT_LOCK_EXPLANATION` under the pickers, and `PAID_TIER_SUMMARY[0]` in the paid half below.
 *
 *  ⚠️ AND IT WENT STALE ONCE ALREADY. Until 2026-08-08 it read "scored for the common league
 *  presets" — true while all 14 preset boards were free, false the moment the tier narrowed, and
 *  invisible either way because nothing renders differently when copy stops being accurate. */
export const FREE_TIER_SUMMARY = {
  title: "This is free, and every number on it is real",
  detail:
    "Every player we project, every ranking, every 80% range and the market ADP beside it — no account, no trial, and no number quietly withheld. It is the same board for everyone, which is exactly what makes it free.",
} as const

/** The paid half, in the two categories the entitlement actually splits on, plus the format lever.
 *  Each `title` names the capability in the user's words; `detail` says what it does, never how well
 *  it does it. */
export const PAID_TIER_SUMMARY: readonly { title: string; detail: string }[] = [
  {
    title: "Every scoring format, at your league's size",
    detail:
      "Half-PPR, standard, superflex, three-receiver, and ten- or twelve-team — each one re-scored, not relabelled. League size moves the replacement level, so it moves the ranking.",
  },
  {
    title: "Your league, not a preset",
    detail:
      "Save your league's real scoring, roster shape and size, and the whole board re-scores against it — including value over replacement, which depends entirely on how many of each position your league actually starts.",
  },
  {
    title: "The tools that turn a board into a pick",
    detail:
      "The draft optimizer, and the in-season calls — waivers, trades, start/sit — worked in your league's scoring rather than left as an exercise.",
  },
]

// ══ THE FORMAT LOCK — what a visitor reads on a preset they cannot open ═════════════════════════
//
// Rendered on the format/size controls themselves, so the boundary is legible AT the control rather
// than only in a block underneath it. Two rules this copy is written to:
//   • It says the format is a MEMBERSHIP feature, not that the numbers behind it are better. The
//     free board is the same model; a different preset is a different SCORING of it.
//   • It never implies the visitor is missing an edge. `best_alpha = 0`.

/** Suffix on a locked option's label in the format/size pickers. Terse by necessity — it sits
 *  inside a dropdown row — with `FORMAT_LOCK_EXPLANATION` carrying the actual sentence. */
export const FORMAT_LOCK_SUFFIX = "Members"

/** The sentence under the pickers when the caller can only open the free preset. */
export const FORMAT_LOCK_EXPLANATION =
  "Full-PPR at twelve teams is free for everyone. The other scoring formats and league sizes are re-scored for members — a different format is a different set of numbers, not a different label on these."

/** Heading when a board REFUSED rather than came back empty — a stale stored selection, or the
 *  window where the frontend has shipped and the API has not (NF-C0). */
export const FORMAT_LOCK_TITLE = "That format is part of a membership"

/** Under the Season Projections "reference scoring" picker, where the same lock applies to a
 *  control that is NOT the board's format picker — the page is scoring-independent and this only
 *  chooses which reference total the table shows and sorts by. */
export const REFERENCE_SCORING_LOCK_NOTE =
  "The reference total shown here is full-PPR, which is free for everyone. Half-PPR and standard are re-scored for members."

/** The player page's per-format tiles, where the two paid ones render a lock instead of a number. */
export const FORMAT_TILE_LOCK_SUB = "Part of a membership"

// ── The raw projected stat line ─────────────────────────────────────────────────────────────────
//
// ⚠️ WHY THIS IS GATED AT ALL, since it is the one piece of this that is not obviously a "format".
// The per-format totals differ ONLY by how receptions are scored, so a visible reception count
// makes the paid numbers exact arithmetic: `half = full − 0.5 × rec`, `standard = full − 1.0 × rec`.
// Measured on a real served player — full 178.4, half 147.5, standard 116.5, receptions 61.9 —
// both identities hold to a tenth. Locking the totals while printing the receptions beside them
// would be a paywall anyone can do in their head, on the page that shows both.
//
// ⛔ It is NOT claimed as anti-scraping. The free board is scrapeable by design and that was
// accepted when this tier was drawn; this is about not printing the answer next to the question.

export const STAT_LINE_LOCK_TITLE = "The projected stat line is part of a membership"

export const STAT_LINE_LOCK_DETAIL =
  "Targets, receptions, yards and touchdowns — the projected production the scoring formats are applied to. Members see the full line for every player, in every format."

/** ...and the entitled version of the same refusal, which is a genuine fault and must not be
 *  dressed up as one. */
export const BOARD_LOAD_ERROR_DETAIL =
  "We couldn't load this board just now. Refresh, or pick another format while we look into it."

// ⚠️ A one-line `FREEMIUM_BOUNDARY_LINE` was written here for "a compact surface that has no room
// for the two blocks above" and then DELETED, because nothing renders it. An exported copy constant
// with no caller reads as shipped wording — the NF-C0e "wired ≠ invoked" shape, one domain over —
// and the next surface to want a one-liner should reach for `DECISION_SUPPORT_LINE`, which is the
// same promise and is actually rendered. Add a second one only when something calls it.

/** The heading over the paid half, and the CTA label under it.
 *
 *  ⚠️ THESE ARE CHROME, NOT CLAIMS — and they live here anyway. `test_freemium_tier.py` asserts
 *  that NO prose is written inline in `FreemiumBoundary`, without trying to distinguish a heading
 *  from a promise. That distinction is exactly what a guard cannot make and what a well-meaning
 *  copy edit erodes: an exception list for "just a heading" is how the first claim gets typed into
 *  a component. One rule, no exceptions, and the screening covers everything the surface renders. */
export const PAID_TIER_HEADING = "What a membership adds"
export const MEMBERSHIP_CTA_LABEL = "See membership options"

/** The standing statement of what the served board actually is, for a surface that renders without
 *  the artifact. Mirrors `build_claim`'s `architecture` note; when the artifact IS available,
 *  prefer `claim.architecture` so there is one string, not two. */
export const ARCHITECTURE_CAVEAT =
  "Our projected points come from a model that never looks at the draft market. A second model sets the order players are ranked in, and at most positions that order blends the market's own consensus with ours — so our ranking is not an independent read on the market."

// ══ G100-C1 — ONE FREE PERSONALIZED LEAGUE ═══════════════════════════════════════════════════════
//
// The free tier now includes a board re-scored for ONE league the user configures themselves. That
// makes a new kind of claim available to overclaim with, and it is a tempting one: the whole point
// of the screen is that the numbers MOVED, so the copy naturally reaches for "we found value the
// market missed". ⛔ It may not. What we can honestly say is narrow and it is enough:
//
//   ✅ "these are YOUR league's numbers, and here is what changed"   — arithmetic we performed
//   ✅ "value over replacement, in your scoring"                     — a definition
//   ⛔ "players the consensus is undervaluing"                       — a claim about the MARKET
//   ⛔ "sleepers", "steals", "out-draft your league-mates"           — the same claim, dressed up
//
// The delta is between TWO OF OUR OWN BOARDS. It says nothing whatsoever about ADP, consensus or
// anyone else's rankings, and a reader will assume otherwise unless the copy says so — which is
// what `LEAGUE_DELTA_DEFINITION` exists to do. `best_alpha = 0`.
//
// Screened by `test_nf_tr1_claim_copy.py`, which parses this file's string literals through the
// export's `_CLAIM_DENYLIST` plus the governance gate.

/** The activation screen's headline — the question the product has to answer visibly. */
export const MY_LEAGUE_HEADING = "What changed because it's your league"

export const MY_LEAGUE_BLURB =
  "The same season projection, re-scored under your league's rules and roster shape, then compared against the free board everyone else sees."

/** ⭐ THE LOAD-BEARING SENTENCE ON THE SCREEN. Without it a reader takes a movement column to be a
 *  claim about the market, because that is what every other fantasy product means by one. */
export const LEAGUE_DELTA_DEFINITION =
  "Movement is between two of our own boards — the free full-PPR, twelve-team board and yours. It is a measure of how much your settings matter, not a view on where anyone else is drafting."

/** Why a player moved. Stated as a mechanism rather than an insight, because it IS one: replacement
 *  level is a function of the roster shape and league size, and nothing here is a prediction. */
export const LEAGUE_DELTA_MECHANISM =
  "A player moves when your scoring changes his point total, or when your starting requirements change how many players at his position are worth having at all. Both are arithmetic on settings you entered."

/** Under the risers/fallers blocks. Keeps the reader from treating a small move as a signal — the
 *  same discipline as the League Board's "read the gaps, not the decimals". */
export const LEAGUE_DELTA_UNCERTAINTY =
  "Small moves are noise inside the 80% ranges these projections carry. A player crossing several positions in your scoring is the part worth acting on."

/** VOR, as the free tier is allowed to describe it. ⚠️ "in your scoring" is the whole claim — it is
 *  a decision AID, and the draft-state-aware version is the paid one. */
export const LEAGUE_VOR_DEFINITION =
  "Value over replacement is a player's projected points minus the points of the first player at his position who does not start anywhere in your league. It is a way to compare a quarterback to a running back on one board."

/** The empty state, before a league exists. Names both routes in, because the manual editor is the
 *  guarantee underneath the importer rather than a fallback for when it fails. */
export const MY_LEAGUE_EMPTY_TITLE = "Set up your league to see your own board"
export const MY_LEAGUE_EMPTY_DETAIL =
  "Import it from Sleeper, Yahoo or ESPN, or enter the scoring and roster by hand. Either way you get the same board — one league is included with a free account."

/** At the control, when the caller is at their quota. States the boundary where they meet it, rather
 *  than letting them fill in a form the API is going to refuse (the freemium build's pattern). */
export const LEAGUE_QUOTA_REACHED_TITLE = "You're using your free league"
export const LEAGUE_QUOTA_REACHED_DETAIL =
  "A free account keeps one personalized league. You can edit or replace this one whenever you like; members keep several and can switch between them."

/** ⚠️ A LAPSED SUBSCRIBER, whose stored leagues outnumber their quota. This state is easy to render
 *  as an accusation or as a silent disappearance; it must be neither. Their configs are all still
 *  there and still deletable — what is paused is the board we compute from them. */
export const LEAGUE_WITHHELD_BY_QUOTA_DETAIL =
  "Your other saved leagues are still here — a free account personalizes one at a time. Nothing has been deleted, and you can choose a different one in League Settings."
