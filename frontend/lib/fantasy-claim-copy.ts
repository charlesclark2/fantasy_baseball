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
// figure. (Until 2026-08-15 the copy also said "and it stays conservative at running back" — true
// of the incumbent, whose per-game RATE under-projected the RB tier by ~20%; NF-TR2b's served level
// recalibration removed most of that, and what remains at RB is inside the noise, so the RB clause
// came out rather than stand as a claim about a residual we measured as noise. The Track Record
// page's per-position table is where any position-level residual is disclosed, derived from data.)

/** The column/tile label for the full-slate reading. "Rate" rather than "if healthy" deliberately:
 *  "if healthy" reads as a PREDICTION about a specific player staying healthy, which is precisely
 *  what this number does not claim. */
export const FULL_SEASON_RATE_LABEL = "Full-season rate"

/** The tappable definition behind that label (rendered through `InfoTip`, so it opens on TAP — the
 *  E9.63/NF3 touch lesson). */
export const FULL_SEASON_RATE_DEFINITION =
  "The same projection, stretched back out to a full seventeen games: expected points divided by expected games. It answers “what is he worth in the weeks he plays?”, which is the fairer way to compare two players whose injury risk differs. It is not a prediction that he plays all seventeen — the expected-points column beside it is the number that prices that in, and it is the one our rankings are built on. It is also our own arithmetic, not a figure reconciled against anyone else's published projections."

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
  // ⭐ NF-LEAK1 RIDER — THE PERK THAT BACKS A CLAIM WE WERE ALREADY MAKING.
  //
  // `scoring_probe_guard.throttle_message` tells a throttled free caller to "subscribe for unlimited
  // edits". Until this entry existed, that sentence was the ONLY place the product said so, and it
  // was said at the worst possible moment — inside a 429, to someone who had just been refused. A
  // benefit that appears only in an error message is not a benefit anyone can find before they hit
  // it, and it reads as a penalty invented on the spot.
  //
  // ⛔ NO NUMBERS. The budget's capacity and refill rate are the attacker's cost model (see that
  // module's header — they were tuned against a measured reconstruction plan), and publishing them
  // hands an extraction walk its exact schedule. "A limit generous enough that ordinary tuning never
  // meets it" is both true and all a real user needs; the exact figures stay in the code.
  {
    title: "Unlimited scoring edits",
    detail:
      "Retune your league's scoring as often as you like. A free account can edit too — there is a rate limit generous enough that ordinary tuning never reaches it — but a membership takes the ceiling off entirely.",
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

// ══ E9.61 — THE SAME DELTA, NOW ON THE BROWSE BOARDS ═════════════════════════════════════════════
//
// My League is the ACTIVATION screen and leads with the delta. Rankings and the League Board are
// the HABITUAL surfaces, and a returning user browsing them wants the same quantity as a column.
// Both readings are legitimate; what is not legitimate is two labels for one number.

/** ⭐ THE COLUMN HEADER, and the one string on this surface that has to be spelled out.
 *
 *  Every other delta column in this product — and in the category — means "versus ADP", i.e. versus
 *  the market. This one does not: it is the distance between two of OUR boards. A bare "Δ", "Move"
 *  or "vs board" inherits the market reading by default, so the header names the comparison
 *  outright and `LEAGUE_DELTA_DEFINITION` rides on it as the tooltip.
 *
 *  ⚠️ ONE constant for all three renderers (My League, Rankings, League Board). My League shipped
 *  with "vs free board" and the boards would have arrived with something else; the same number
 *  under two names on adjacent pages is how a reader concludes they are two different numbers. */
export const GENERIC_DELTA_LABEL = "vs our generic board"

/** The band above a personalized browse board. Says WHICH board is selected is doing the work, and
 *  sends the reader to the screen that explains WHY — rather than re-deriving the explanation on a
 *  page whose job is browsing. */
export const GENERIC_DELTA_BAND_DETAIL =
  "You're looking at this board re-scored for your league. The column on the right is how far each player has moved from our generic board — not from where anyone else is drafting."

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

// ══ NF-C6P2 — THE POST-DRAFT ROSTER REPORT ═══════════════════════════════════════════════════════
//
// The conversion moment: a user finishes their draft, imports the result, and reads what they
// actually built. It is the single most tempting surface in the product to overclaim on, because
// the reader is primed for a verdict — "did I win my draft?" — and we have not measured anything
// that answers that question.
//
//   ✅ "your starters project to N points, with an 80% range of X–Y"  — arithmetic we performed
//   ✅ "you are above/below what an average team in THIS league holds at RB" — a comparison of our
//      own numbers against our own replacement levels
//   ✅ "week 8 costs you the most, and here is why"                   — a re-fill of your lineup
//   ⛔ "you drafted the best team", "a playoff roster", a grade, a rank against the other teams
//   ⛔ anything about winning, and anything implying we know the other eleven rosters
//
// ⭐ WE CANNOT SEE THE OTHER TEAMS. The platform-import red line means we hold the caller's own
// roster and nothing else, so every league-relative statement here is against the BOARD's own
// replacement and starter demand — never against real opponents. Two constants
// (`REPORT_LEAGUE_BASELINE_NOTE`, `REPORT_WAIVER_NOTE`) exist to say that out loud on the surface,
// and they are not optional garnish: without them a reader takes "above average" to mean "above the
// other eleven managers", which is a claim about data we do not have.
//
// Screened by `test_nf_tr1_claim_copy.py` alongside every other string in this file.

export const ROSTER_REPORT_HEADING = "Your roster, read against your league"

export const ROSTER_REPORT_BLURB =
  "Your drafted roster scored under your league's own rules, then measured against the replacement level and starter demand that same league creates. Every figure below is a sum of the projections on your board — nothing here predicts a result."

/** ⭐ THE UNCERTAINTY SENTENCE, and the one that had to be written most carefully.
 *
 *  A team total is a SUM of distributions, and how you combine them is an assumption with a known
 *  direction of error. Independence under-disperses a correlated sum — NF-W7b measured exactly that
 *  on a DST leg — and real rosters co-move (one offense, shared game script, a stacked pair). So the
 *  surface renders the independent band AND states the fully-correlated one beside it, rather than
 *  printing one number and calling it "the range". */
export const ROSTER_REPORT_RANGE_NOTE =
  "The total is exact — expected points add up however your players' seasons turn out. The range is not: it combines each player's own 80% range assuming their seasons are independent of one another. Real rosters move together to some degree, so treat this as the narrow end; the wider figure beside it is what the range becomes if every season moved in step."

/** How a position's "above/below average" figure is built. Names the baseline explicitly. */
export const REPORT_LEAGUE_BASELINE_NOTE =
  "Above or below is against an average team in a league with your settings — the players your league's roster shape expects to start, shared out by team count. It is not a comparison against the other managers in your league; we do not hold their rosters."

/** Value over replacement, restated for a reader who arrived here straight from a draft. */
export const REPORT_POSITION_DEFINITION =
  "Each position is scored by value over replacement: your starters' points minus the points of the first player at that position who does not start anywhere in your league. That is what makes a quarterback and a running back comparable on one line."

export const REPORT_BENCH_NOTE =
  "A bench is optionality, not points. What matters is how many of these players would be starting somewhere in your league, because those are the ones covering a bye or an absence."

export const REPORT_BYE_NOTE =
  "Each week is your lineup re-filled with that week's byes removed, in points per game played. A week costs you nothing if your bench covers it — which is the useful thing to know before waivers open."

/** ⚠️ THE MOST MISREADABLE SECTION ON THE PAGE, so its note is the longest. "Injury concentration"
 *  invites a reader to think we are forecasting injuries. We are not: expected games is already
 *  inside the points, and this section only shows where that discount and the roster's dependence on
 *  one player are concentrated. */
export const REPORT_FRAGILITY_NOTE =
  "Projected games are already priced into the points above — a player expected to miss time is projected lower for it. Nothing here forecasts an injury. This is where your projection is concentrated, and how much a lineup slot drops if the best body on your bench has to take it."

/** ⛔ THE FALLBACK, AND IT IS STILL THE TRUTH WHENEVER WE DO NOT HOLD THE WHOLE LEAGUE — a
 *  hand-entered league, one imported before NF-C6P3 shipped, or a partial capture. The report picks
 *  between this and `REPORT_FREE_AGENT_NOTE` from what it actually holds
 *  (`RosterReport.leagueRosters.complete`), never from which sentence reads better. */
export const REPORT_WAIVER_NOTE =
  "We do not hold your league's other rosters, so these are not waiver claims — they are the best players outside the pool a league your size drafts, aimed at the gaps above."

/** ⭐ NF-C6P3 — the sentence we can now make when every roster in the league is stored: a player on
 *  NOBODY's roster is an observation, not a definition.
 *
 *  ⚠️ THE SNAPSHOT HEDGE IS NOT OPTIONAL AND MAY NOT BE TRIMMED. We read the league once, at import,
 *  and never again — so a player picked up an hour later is still listed here. "Free agent when you
 *  imported" is honest; "on waivers now" is a claim about a live read this product does not make.
 *  Dropping the clause would turn a true sentence into a false one without changing a number. */
export const REPORT_FREE_AGENT_NOTE =
  "These are players on nobody's roster in your league — we hold every team's, so this is a real free-agent pool rather than a guess at one. It is the roster picture from when you imported the league; we do not re-read it, so anyone claimed since then will still be listed."

/** The partial-coverage state, which must read as an ABSENCE rather than as a weaker version of the
 *  sentence above. A pool computed from some of the rosters would list the missing teams' players as
 *  free agents — a confidently wrong list that looks exactly like a right one — so we do not compute
 *  one, and this says why. */
export const REPORT_FREE_AGENT_PARTIAL_NOTE =
  "We hold some of your league's rosters but not all of them, so we can't tell you who is genuinely unowned without guessing about the teams we're missing. Re-import the league to pick the rest up."

// ══ NF-C6P3 — THE LEAGUE COMPARISON'S COPY ═══════════════════════════════════════════════════════
//
// ⛔⛔ A STANDINGS-SHAPED TABLE ANSWERS "DID I WIN MY DRAFT?" WHETHER OR NOT IT WAS ASKED, and that
// is the one question this product has measured nothing about. The strings below are the boundary:
// a rank ON THIS MEASURE is a fact about arithmetic we performed; a projected finish, playoff odds
// or a win probability would need a weekly-variance schedule simulation that does not exist, and
// `best_alpha = 0`.
//
// ⭐ THE THREE CAVEATS SHIP WITH THE TABLE, NOT BEHIND A DISCLOSURE, and each names a way the number
// is weaker than it looks that a reader cannot recover for themselves. A caveat behind a click is a
// caveat that did not render.

export const REPORT_COMPARISON_HEADING = "Your roster against the rest of your league"

/** ⚠️ THE SENTENCE THAT DEFINES WHAT IS BEING RANKED, and it has to do that in its FIRST clause —
 *  a reader who stops after the heading must already know this is about projected starter points
 *  and not about where they will finish. */
export const REPORT_COMPARISON_NOTE =
  "Every team's roster filled by our optimizer and totalled on your league's own board — a ranking of projected starting points, and nothing more. It is not a projected finish and not a chance of winning anything: those need a week-by-week schedule simulation we have not built."

/** Caveat 1 — the construction. */
export const REPORT_COMPARISON_CAVEAT_LINEUP =
  "We do not know the lineup another manager will actually start, so every team here is filled the same way yours is: our best legal lineup from the players on their roster. That flatters every opponent equally."

/** Caveat 2 — the vintage. */
export const REPORT_COMPARISON_CAVEAT_SNAPSHOT =
  "These are the rosters as they stood when you imported the league. We do not re-read it, so a trade or a waiver claim since then is not in here."

/** Caveat 3 — whose opinion this is. ⚠️ The most important of the three and the easiest to drop,
 *  because it is the one that concedes the table is a statement about our model. */
export const REPORT_COMPARISON_CAVEAT_OURS =
  "The order is our projections' opinion. It tells you whose roster our model likes, which is a claim about the model as much as about the rosters."

export const REPORT_COMPARISON_PARTIAL =
  "We only hold some of your league's rosters, so the teams missing from this table are missing from the range and the position too."

export const REPORT_TRADE_NOTE =
  "A shape, not an offer. It says you hold startable depth in one place and your thinnest starters in another; what a trade is worth, and whether anyone would take it, is not something we have measured."

/** ⚠️ The first-week lineup's honest label. The weekly model is not published yet, so this is the
 *  SEASON projection expressed per game played — which is a different and weaker thing than a week-1
 *  forecast, and saying so is the whole point of the string. */
export const REPORT_FIRST_WEEK_NOTE =
  "Built from the season projection expressed per game played, not from a week-by-week model — that one is still in the lab. It answers 'who are my best nine' rather than 'who has the best matchup'."

// ══ NF-C6b — THE CROSS-LEAGUE PORTFOLIO ROLLUP'S COPY ════════════════════════════════════════════
//
// ⛔⛔ RANKING TEAMS ACROSS DIFFERENT LEAGUES ADDS A FAILURE MODE THE IN-LEAGUE COMPARISON DOES NOT
// HAVE, and it is the whole reason this block exists separately. NF-C6P3 ranks teams inside ONE
// league, where every total was produced by the SAME rules, so the order is a clean statement about
// rosters. Here the totals come from DIFFERENT rule sets: a half-PPR league pays 0.5 a reception and
// a standard league pays nothing, so the SAME players total more in one than the other. The order is
// therefore NOT a roster-strength ranking, and a reader who is not told that will read it as one —
// it is the single most misreadable thing on the surface.
//
// ⭐ THE CAVEATS RENDER WITH THE TABLE, NOT BEHIND A DISCLOSURE (NF-C6P3's rule, and NF-C6P3 itself
// shipped a caveat behind a click that never rendered). A caveat behind a click is a caveat that did
// not render.

export const PORTFOLIO_HEADING = "Your teams"

/** The label for the numbers themselves. ⚠️ "Full-season" and "pre-kickoff" are both load-bearing:
 *  the weekly model is not published, so there is no per-game or week-1 figure to show, and a season
 *  total divided into a per-game rate would be false precision rather than a weekly projection. */
export const PORTFOLIO_TOTAL_LABEL = "Full-season projected points (pre-kickoff)"

/** ⭐ THE TWO READINGS, and the labels are the boundary between them. As-set is what the reader's
 *  platform says they are starting; best-possible is what the roster is worth with the lineup right.
 *  Neither is "your score" — both are full-season projections before a snap has been played. */
export const PORTFOLIO_AS_SET_LABEL = "Your current starters (projected)"
export const PORTFOLIO_BEST_LABEL = "Your best possible lineup (projected)"
export const PORTFOLIO_GAP_LABEL = "Points on your bench"

/** ⭐⭐ THE HERO NUMBER, AND THE ONLY ONE ON THIS SURFACE WITH NO CROSS-LEAGUE CONFOUND. Both totals
 *  come from the SAME league's scoring, so the difference between them is immune to the
 *  scoring-format problem that keeps the ranking a rough guide. It is also the one figure here a
 *  reader can act on. */
export const portfolioGapHeadline = (points: string): string =>
  `Leaving ${points} projected points on your bench`

export const PORTFOLIO_GAP_NONE = "Your current starters already are our best lineup for this roster."

export const PORTFOLIO_GAP_NOTE =
  "The difference between the lineup your platform reports and the best legal one we could field from the same roster. Both are scored on this league's own rules, so this figure is not affected by the scoring differences between your leagues."

/** ⚠️ THE SENTENCE THAT DEFINES WHAT IS BEING RANKED, and it does it in the FIRST clause — a reader
 *  who stops after the heading must already know this is a points total and not a standing. */
export const PORTFOLIO_NOTE =
  "Ordered by each roster's best possible lineup, totalled on that league's own scoring — a rough guide to where your rosters stand, not a precise ranking. It is not a projected finish and not a chance of winning anything: those need a week-by-week schedule simulation we have not built."

/** ⭐ Caveat 1 — THE ONE THAT IS UNIQUE TO THIS SURFACE. Without it the table reads as "which of my
 *  rosters is best", which the numbers cannot support when the scoring differs between leagues.
 *  ⚠️ It also names the SECOND cross-league confound — roster size — because a league that starts
 *  more players totals more for that reason alone. */
export const PORTFOLIO_CAVEAT_FORMATS =
  "Your leagues do not all score the same way, and they do not all start the same number of players, so these totals are not like-for-like. A league that pays for receptions produces a bigger number than one that does not, for the very same players. Treat the order as a rough guide under each league's own rules — not as a verdict on which roster is stronger. The bench figure is the one number here that is not affected."

/** Caveat 2 — the lineup, now that BOTH readings are shown. The optimizer's lineup is a construction
 *  and the surface should not imply we know what anyone will actually start. */
export const PORTFOLIO_CAVEAT_LINEUP =
  "“Best possible” is our best legal lineup from the players on your roster — a construction, not a prediction of what you will start. “Current starters” is whatever your platform reported when you imported the league, which before Week 1 is often just what the draft left behind."

/** Caveat 3 — the vintage. Same fact as the roster report's, said again here because this surface is
 *  reachable without ever opening that one. */
export const PORTFOLIO_CAVEAT_SNAPSHOT =
  "These are the rosters as they stood when you imported each league. We do not re-read them, so a trade or a waiver claim since then is not in here."

/** ⚠️ Shown only when it is true, and it concedes that the ORDER — not just the totals — may be
 *  wrong. A team missing a starter's points can rank below one that is complete purely for that
 *  reason, and a reader cannot recover that from the number itself. */
export const PORTFOLIO_UNDERSTATED_NOTE =
  "At least one team has a starter we could not match to a projection. Its points are missing from that team's total, so the total is understated and the order may be affected."

/** The per-card total's own caveat when that card is the one missing a starter. */
export const portfolioUnscoredNote = (n: number): string =>
  `${n} ${n === 1 ? "starter is" : "starters are"} not matched to a projection, so this total is understated by whatever ${n === 1 ? "that player is" : "those players are"} worth.`

/** ⚠️ Shown when the roster cannot fill the league's starting lineup. Without it, "best possible
 *  lineup" reads as a full lineup when it is a total over the slots we could fill — a small number
 *  and a wrong one are different things. */
export const portfolioUnfilledNote = (n: number): string =>
  `This roster cannot fill ${n} starting ${n === 1 ? "slot" : "slots"}, so the best-possible figure is a total over the slots it can fill.`

// ── The empty states. Four different facts, four different messages ─────────────────────────────
//
// ⚠️ These must not be collapsed into one "nothing to show". "You have no league", "you have not
// picked your team", "your league has not drafted" and "we could not read the board" are four
// different situations with four different next actions, and NF-C6 already shipped the bug where two
// of them shared a message and told a user to do something they had already done.

export const REPORT_EMPTY = {
  "no-league": {
    title: "Import your league to see your roster report",
    detail:
      "Pull it in from Sleeper, Yahoo or ESPN, or enter the scoring and roster by hand. One personalized league is included with a free account.",
  },
  "no-team-linked": {
    title: "Pick your team and the report will build itself",
    detail:
      "Your league is saved, but we do not know which of its teams is yours. Re-import it and choose your team on the review step.",
  },
  "not-drafted": {
    title: "Nothing drafted yet",
    detail:
      "Your team is linked and the platform reports no players on it — usually because the draft has not happened. Come back and re-import once it has, and this page fills in.",
  },
  "no-board": {
    title: "We could not build your board just now",
    detail:
      "This one is on us, not on your league. Refresh in a moment; if it keeps happening the projections may be mid-publish.",
  },
  "nothing-matched": {
    title: "We could not match your roster to our board",
    detail:
      "Your league and team are saved, but none of the rostered players resolved to a player we project. Re-importing usually fixes it.",
  },
} as const

// ── The season upgrade prompt — the conversion moment ───────────────────────────────────────────
//
// ⛔⛔ THIS SELLS ONGOING ANALYSIS, NOT AN OUTCOME. The reader has just been shown a real read on
// their roster; the honest offer is that the read keeps arriving all season in their league's own
// scoring. It is NOT "and then you will win", and it may not imply the free report is missing an
// edge. `best_alpha = 0`, and the denylist screening covers these strings like every other.

export const REPORT_UPGRADE_HEADING = "Keep this read going all season"

export const REPORT_UPGRADE_DETAIL =
  "This report is a snapshot of draft day. A membership keeps it current: your board re-scored as projections move, start/sit and waiver calls worked in your league's scoring rather than left to you, several leagues instead of one, and the ranges beside every number so you can see how much of a call is real."

export const REPORT_UPGRADE_CTA = "See membership options"
