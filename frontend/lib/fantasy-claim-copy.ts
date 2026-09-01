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

// ══ NF-C8 — THE AVAILABILITY FLAG ══════════════════════════════════════════════════════════════
//
// The projected-games column and the expected-points label above already make the discount
// EXPLICABLE. They do not make it VISIBLE: a drafter scanning a board meets a lower number and a
// lower rank, and nothing on the row says which of those is availability until he goes looking. The
// flag is the glance-level version of the same disclosure — a colour on the games figure for the
// rows where the discount is doing real work, with the sentence one tap behind it.
//
// ⛔⛔ THE ONE RULE THIS BLOCK EXISTS FOR, AND IT IS ABSOLUTE: THIS MAY NOT FORECAST AN INJURY.
// What we know is a property of OUR PROJECTION — we project this player for fewer than a full slate
// of games. What we do NOT know, have never modelled, and could not defend, is that a particular
// player is hurt, will get hurt, or will miss particular weeks. Those are medical predictions. The
// distinction is invisible in a UI (an amber chip reads as "injury risk" unless the words say
// otherwise) and it is one careless verb away in copy — "will miss", "expected to miss", "injury
// risk", "out for" all cross it. `test_nf_c8_availability_flag_copy.py` holds a forbidden-verb list
// over these constants for exactly that reason.
//
// ⛔ AND IT MAY NOT ABSORB THE RESIDUAL, same rule as `EXPECTED_POINTS_NOTE` one block up.
// Availability carries most of the measured level shift and not all of it. A flag that said "this
// is why his number is low" would be using an honest mechanism to bury a dishonest amount, and it
// would do it on a far higher-traffic surface than the track record.
//
// ⛔ NO THRESHOLD IN THE PROSE. The constants that decide which rows flag live in `lib/fantasy.ts`
// (`LIMITED_AVAILABILITY_GAMES` / `HEAVILY_LIMITED_AVAILABILITY_GAMES`) and are display quantities;
// typing "below 14 games" into a sentence here would (a) duplicate them somewhere no test pins and
// (b) read as a published finding rather than as a rendering choice. The copy says "fewer than a
// full season" and lets the per-player value — read from the served artifact — carry the size.

/** The chip's own accessible name, and the heading of the definition behind it. Deliberately names
 *  the PROJECTION as the subject ("we project") rather than the player ("he will play"): the first
 *  is a statement we can defend, the second is a forecast about a person. */
export const AVAILABILITY_FLAG_LABEL = "Limited projected availability"

/** The one-line summary rendered at the top of the flag's definition, with the served per-player
 *  games figure substituted for `{games}` at render time.
 *
 *  ⚠️ `{games}` IS A PLACEHOLDER, NOT A FIGURE, and that is the whole reason this constant reads
 *  oddly out of context. The rule from the head of this file — no measured number typed into copy —
 *  applies to a games value exactly as it applies to a bias or an interval: a number typed here
 *  cannot be reconciled against the artifact it describes. The value is read per-player from the
 *  served payload and interpolated by the component. */
export const AVAILABILITY_FLAG_SUMMARY =
  "Projected {games} games — limited availability priced in."

/** The tappable definition behind the flag. Says what the flag IS, what it is NOT, and points at
 *  the expected-points explanation rather than restating it. */
export const AVAILABILITY_FLAG_DEFINITION =
  "We project this player for fewer games than a full season, and his point total is already built on that smaller number of games rather than on a full slate. This is a statement about our projection, not a diagnosis: the games figure is an average across everything that could happen to him, so it is not a forecast about his health and it does not name weeks he sits out. It is also not the only reason a projection lands where it does — read it next to the expected-points definition, which is where the rest of that story lives."

/** The freshness line inside the flag's definition (NF-FRESH2's rule, applied to the one input this
 *  flag actually rests on).
 *
 *  ⭐⭐ NF-C10 — PROVENANCE ONLY. THE WORD DROPPED HERE IS "STATUS", AND DROPPING IT IS THE STORY.
 *  This line renders directly beneath the NF-C9 disclosure whose whole point is that we hold a
 *  player's weekly designation and DO NOT act on it. "Injury and roster STATUS as of {date}" reads
 *  as a claim about the player's standing — i.e. that we know it AND have applied it — so the two
 *  lines contradicted each other on every surface they share. "Injury/roster FEED as of {date}"
 *  says only what is true and all that this line was ever for: when the input we read was captured.
 *  A vintage stamp describes a FEED, never a player. (PM-ruled Option 1, 2026-08-23.)
 *
 *  ⚠️ ABSENT ≠ NULL, and both directions matter here as much as they do on the provenance strip:
 *  a payload that never carried the stamp gets NO line at all (inventing "unknown" during a routine
 *  deploy window would put a scary word under every flag), while a stamp the exporter looked for and
 *  could not resolve renders as unknown rather than being silently dropped — an unevaluable check is
 *  never scored healthy (NF1.7 (a)). */
export const AVAILABILITY_DATA_AS_OF_PREFIX = "Injury/roster feed as of"

export const AVAILABILITY_DATA_AS_OF_UNKNOWN = "unknown"

// ══ NF-C9 — THE WEEKLY GAME-STATUS DESIGNATION: DISCLOSED, NOT MODELLED ════════════════════════
//
// ⭐ THE GAP THIS DISCLOSES, TRACED RATHER THAN INFERRED (NF-C8's finding,
// `ablation_results/nf_c8_injury_designation_gap.md`). The availability discount has exactly one
// entry point and it is narrow by construction: `season_projection.injury_availability_games` caps
// projected games only for a formal ROSTER TRANSACTION (injured reserve / PUP / non-football-injury
// / suspension), and `sleeper_injuries_source.map_injury_status` returns NO OVERRIDE for a weekly
// game-report tag. So **Questionable, Doubtful and Out apply a discount of exactly zero** — and a
// reader who meets an "Out" player at a normal-looking projected-games figure reasonably assumes we
// marked him down. We hold the designation. We do not act on it. Until NF-C8 put a flag on the
// games figure, nothing on any surface said so.
//
// ⛔⛔ THE ONE RULE THIS BLOCK EXISTS FOR: THIS IS A DISCLOSURE, NOT AN ADJUSTMENT. Every sentence
// here has to survive a reader asking "so is it in the number or not?" with the answer NO. The
// tempting failure is not a lie, it is a HEDGE that reads as one — "we take his status into
// account", "reflected in the projection", "priced in", "factored in", "adjusted for" — each of
// which would be false about this channel while sounding like ordinary product copy.
// `test_nf_c9_designation_disclosure.py` holds that list over these constants.
//
// ⛔ AND IT MAY NOT FORECAST AN INJURY, for exactly the reasons the NF-C8 block above gives, only
// more sharply: this constant renders a real designation about a NAMED PERSON, so the distance
// between "a third party listed him Questionable for one game" and "he is hurt and will miss time"
// is one sentence of carelessness. The SAME `_INJURY_FORECAST_VERBS` screen runs over these
// strings, and it is deliberately ABSOLUTE (negation-blind) — see that suite's note on why a
// negation WINDOW is the wrong repair: "we do not think he will miss time" is still a medical
// prediction. The refusal is expressed WITHOUT the banned tokens.
//
// ⛔ NO DURATION, EVER. A weekly designation carries none: "Out" means out of ONE game, and the
// multi-week absence a news report describes is a NEWS fact, not a status fact. Copy that implied a
// length would be inventing the single quantity that makes this hard to model at all.
//
// ⛔ NO STATUS TYPED HERE. `{status}` is a placeholder filled from the served payload, the same
// rule the head of this file applies to every measured figure: a designation typed into a component
// cannot be reconciled against the feed it came from. The vocabulary lives in
// `sleeper_injuries_source.WEEKLY_DESIGNATIONS`, which is where it was measured.

/** The chip's accessible name and the heading of the definition behind it. Names the REPORT as the
 *  subject, never the player — "listed on a report" is a fact about a document we read; "he is
 *  banged up" is a claim about a person we have no standing to make. */
export const WEEKLY_DESIGNATION_LABEL = "Weekly game-status designation"

/** The one-line summary at the top of the definition. `{status}` is the served designation. */
export const WEEKLY_DESIGNATION_SUMMARY =
  "Listed {status} on the most recent game-status report our injury feed carries."

/** The summary for a value the build cannot interpret — the third state (NF1.7 (a)): the feed said
 *  something, we could not read it, and saying nothing would let that render as a clean bill of
 *  health. ⛔ It deliberately does not print the raw token: publishing a code we decline to define
 *  asks the reader to interpret it for us. */
export const WEEKLY_DESIGNATION_UNKNOWN_SUMMARY =
  "Our injury feed carries a game-status value for this player that we do not recognise, so we are not going to guess at what it says."

/** ⭐⭐ THE SENTENCE THE WHOLE STORY IS FOR. If a copy trim ever takes one line out of this block,
 *  this is the line that must not be it: without it the chip reads as an adjustment we made. */
export const WEEKLY_DESIGNATION_NOT_MODELLED =
  "Our projected-games figure does not take this into account. That number moves only on a formal roster move — injured reserve, the physically-unable-to-perform list, the non-football-injury list, or a suspension — so a weekly designation like this one applies no discount to it at all. We show it because we hold it, not because we have built it into anything."

/** The refusal, in the register the NF-C8 flag uses. Says what a designation IS and what it is not:
 *  one club's filing about one game, not a diagnosis, and carrying no length. */
export const WEEKLY_DESIGNATION_NOT_A_DIAGNOSIS =
  "A designation is what a club filed about one game. It is not a diagnosis, it is not our own read on how a player is doing, and it says nothing about how many games anything lasts."

/** What the chip shows for a value we could not interpret. Lowercase on purpose — it is a state, not
 *  a designation, and title case would make it look like one. */
export const WEEKLY_DESIGNATION_UNKNOWN = "unknown"

// ══ NF-INJ-NEWS-1 — THE REPORTED-ABSENCE STAMP: A HUMAN READ A REPORT, AND WE SAY SO ═══════════
//
// ⭐ THE THIRD, DELIBERATELY SEPARATE INJURY CHANNEL ON THIS BOARD, and the separation is the
// point — the three answer different questions and collapsing any two of them makes at least one
// sentence false:
//
//   `AvailabilityFlag`    (NF-C8)  — "our projection says this player misses time." A MODEL output,
//                                    fired by the projected games number whatever produced it.
//   `WeeklyDesignation`   (NF-C9)  — "the league lists him Questionable, and we do NOT price it in."
//                                    A FEED value, disclosed precisely because the model ignores it.
//   `ReportedAbsence`     (here)   — "a person on our side read a report and lowered his games."
//                                    An OPERATOR JUDGMENT, with the source attached.
//
// The first two are things we OBSERVE. This one is a thing we DID, which is why it is the only one
// that ships a citation and a date-of-entry: the reader is entitled to check the human's work.
//
// ⛔ IT IS NOT A FORECAST AND MUST NEVER READ AS ONE. No return date, no body part, no diagnosis,
// no "expected back in Week N" — that would be a medical claim we have no basis for, and the honest
// duration model that could support one is a separate §0.5 story that has not been run. The copy
// says WHERE the number came from and WHEN somebody decided it. Nothing else.
//
// ⛔ AND IT CLAIMS NO IMPROVEMENT. This mechanism has never been backtested and is not presented as
// making the projection better — it is an interim while the duration model is built. Saying so is
// not a hedge, it is the accurate description; `test_nf_inj_news_1_reported_absence.py` refuses any
// accuracy or forecast phrasing in this block.
export const REPORTED_ABSENCE_LABEL = "Reported absence"

/** The chip's summary. ⚠️ PAST TENSE AND FIRST PERSON on purpose — "we lowered" names an ACT we
 *  performed, where "he is expected to miss N games" would be a prediction about the player. */
export const REPORTED_ABSENCE_SUMMARY =
  "We lowered this player's projected games by hand, on a published report of an expected absence."

/** The honesty line, rendered UNCONDITIONALLY beneath the summary — never behind a click, and never
 *  only on some surfaces. NF-C6P3: a caveat a reader has to open is a caveat most readers never
 *  see, and this is the sentence that stops a manual adjustment reading as a model output. */
export const REPORTED_ABSENCE_MANUAL =
  "This is a manual judgment, not a model output. It has not been tested against outcomes."

/** ⛔ The no-forecast line. The reader is told what we did NOT do, because the natural reading of a
 *  lowered games number is that we know when he is coming back. We do not. */
export const REPORTED_ABSENCE_NOT_A_FORECAST =
  "It is not a medical opinion and not a return date — our projection carries no view on when he plays again."

/** Prefix for the entry date. The date is when the JUDGMENT was made, which is not the same as the
 *  injury-feed vintage the other two chips show, and labelling it loosely would conflate them. */
export const REPORTED_ABSENCE_ENTERED_PREFIX = "Entered"

/** The link out to the source. Required on every stamped row — a manual adjustment with nothing to
 *  check is indistinguishable from a guess, and the citation is the whole difference. */
export const REPORTED_ABSENCE_SOURCE_LABEL = "Read the report"

/** The methodology-panel disclosure. ⭐ It exists so the mechanism is discoverable by a reader who
 *  has NOT happened to hover a chip: a manual override that only announces itself on the rows it
 *  touched is not disclosed, it is merely visible. */
export const REPORTED_ABSENCE_METHOD_DISCLOSURE =
  "A small number of players carry a games projection we lowered by hand, after a published report " +
  "of an expected absence that no official roster move had yet reflected. Those rows are marked and " +
  "carry a link to the report. It is a manual judgment with a source attached, not a model output, " +
  "and it has not been tested against outcomes; we review each entry on a set date and drop it when " +
  "it goes stale. Every other player's games projection is produced by the model alone."

/** Designation → the glyph on the chip.
 *
 *  ⚠️ A LOOKUP, NOT A FALLBACK CHAIN: a designation this map does not know renders VERBATIM (see
 *  `WeeklyDesignation`), never as "unknown". The two are different facts — the exporter refusing to
 *  interpret a feed value is an unknown; a NEWER exporter serving a designation an OLDER client has
 *  not learned yet is a deploy-skew window (NF-C0), and the honest rendering there is the word the
 *  server sent. Q/D/OUT are the codes the game-status report itself uses, so they need no legend;
 *  the full word is always in the accessible name and in the definition. */
export const WEEKLY_DESIGNATION_CODE: Record<string, string> = {
  Out: "OUT",
  Doubtful: "D",
  Questionable: "Q",
}

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

// ── NF-RATE1 — the rate we WITHHOLD, and why the wording has to be this narrow ───────────────────
//
// ⛔ NO FORECAST LANGUAGE AND NO INJURY CLAIM, and none is possible here: this says nothing about
// the player, his health, his role or his season. Like NF-INJ1-C's sibling label it is a statement
// about OUR OWN arithmetic for him — the rate our two published numbers imply is higher than any
// full season a real player has ever produced, so we do not print it. `best_alpha = 0`.
//
// ⚠️ IT MUST KEEP NAMING THE CONDITION A READER CAN CHECK — "higher than any real season" is the
// only part that says WHY, and it is checkable against the very board it appears on. A future trim
// to a bare "withheld" loses that; a trim toward "he is expected to miss time" would be an injury
// forecast we have never made, on a column that is not about availability at all.
//
// ⭐ AND IT SAYS THE TWO NUMBERS BESIDE IT ARE UNAFFECTED, because they are (NF-INJ3b-SHIP ruling
// D3 keeps both served) — a reader who wants this rate can still divide, and the disclosure would
// be misleading if it implied otherwise.

/** The short label on the withheld cell's disclosure. */
export const FULL_SEASON_RATE_WITHHELD_LABEL =
  "rate withheld — higher than any full season on record"

/** The accessible name for the withheld cell, read out instead of a bare em-dash — which a screen
 *  reader announces as nothing at all, i.e. as an empty cell. */
export const FULL_SEASON_RATE_WITHHELD_SR_LABEL = "Full-season rate withheld"

/** The tappable detail behind it. */
export const FULL_SEASON_RATE_WITHHELD_DETAIL =
  "Stretching this player's projection back out to seventeen games implies a season higher than any real player has posted at his position since 2006, so we don't print it here — a number that far outside what football has done tells a drafter nothing. His projected points and projected games are unchanged and still shown beside it."

// ── NF-CSV1 — the same refusal, carried into the file the reader takes away ──────────────────────
//
// THE GAP THIS CLOSES, AND WHY IT IS A SEPARATE ONE. Everything above is a POPOVER: a withheld cell
// on the page is an em-dash a reader can tap, and the tap is where the refusal explains itself. The
// exported CSV keeps the withholding (`fullSeasonRateCsv` → an empty cell) and leaves the
// explanation behind on the page — so the one surface a paying reader actually works from was the
// one that stated nothing. A blank in a spreadsheet reads as "we have nothing", which is the E9.56c
// inversion this family exists to prevent, arriving by a different door.
//
// ⭐ WHY A NOTE **ROW** AND NOT A SENTINEL IN THE CELL. The cell has to stay empty — a `withheld`
// string breaks the column's type for anyone who sorts or averages it, and `0`/`-1` is a wrong
// number rather than an absent one (`fullSeasonRateCsv`'s own note). So the explanation cannot live
// in the column; it lives in one row APPENDED AFTER the data, first cell only, leaving the header
// on row 1 and every data column untouched.
//
// ⭐⭐ THE NOTE IS ASSEMBLED FROM A REGISTRY, ONE CLAUSE PER WITHHELD **CLASS**, and only the
// classes actually present in the exported file contribute. Two reasons, and the second is the one
// that bites: a note listing a class the file does not contain is a false statement about that
// file, and a note hard-coded to today's single class silently stops being complete the moment a
// second withheld class reaches an exported column. `CSV_WITHHELD_CLASSES` is where a second class
// gets added, and the guard suite fails if a registered class has no clause.
//
// 🔎 MEASURED FOR THIS STORY, and recorded rather than assumed (the acceptance criterion asks for
// the check either way): NF-INJ1-C's stat-line withholding does NOT reach this export. It is
// carried per row on `statLineWithheld` and rendered only by `projections-table.tsx` and
// `player-page.tsx`, NEITHER of which has an export; the rankings board is the only `downloadCsv`
// caller in the app, and its column list carries no stat-line column for the marker to apply to.
// So the registry has exactly one member today, and that is a fact about the exported columns
// rather than a simplification. Re-check it if a stat column is ever added to this file.
//
// ⛔ NO FORECAST LANGUAGE AND NO INJURY VERB, exactly as above — this says nothing about a player,
// his health or his season. And ⚠️ IT MUST NOT CLAIM EVERY BLANK IS A WITHHOLDING: the same column
// is blank where there is no expected-games figure to divide by, which is a genuine absence, and a
// note that collapsed the two would make the file dishonest in the other direction. The page
// separates them (a withheld cell is a tappable dotted em-dash, an unavailable one is a plain one);
// the file cannot, and says so.

/** A class of value this export can withhold. One clause per member, below. */
export type CsvWithheldClass = "full-season-rate"

/** The note row's text, in three parts: an invariant lead, one clause per withheld class present,
 *  and a trailer pointing at the surface that carries the full per-row disclosure.
 *
 *  ⚠️ EVERY PART IS A SINGLE LINE. A newline anywhere here would be quoted into a multi-line CSV
 *  field, which is legal CSV and breaks every line-counting reader of this file — including the
 *  row-count contract in `fantasy-board-flows.spec.ts`. Pinned by the guard suite. */
export const CSV_WITHHELD_NOTE = {
  lead:
    "Note — one or more rows in this file have a value withheld. A withheld value is a number we hold and are declining to publish; the columns it is derived from are unchanged and still in this file.",
  clause: {
    "full-season-rate":
      "full_season_rate is blank on a row whose expected_pts and expected_games imply a full-season pace above any season a real player has posted at that position since 2006. That column is also blank where there is no expected-games figure to divide by, which is an absence rather than a withholding, and this file cannot tell the two apart.",
  },
  trailer:
    "The Full-season rate column on the site marks the withheld rows and states why.",
} as const

/** Every withheld class this export knows how to describe, in the order the note lists them.
 *
 *  ⭐ THE NOTE'S ORDER COMES FROM HERE, NOT FROM THE CALLER — so the rendered bytes are a function
 *  of which classes are present and nothing else, which is what makes pinning them meaningful. */
export const CSV_WITHHELD_CLASSES: readonly CsvWithheldClass[] = ["full-season-rate"]

/**
 * The note row's text for a file containing exactly `present`, or `null` when it contains none —
 * in which case the export appends no row at all and the file is what it was before this story.
 *
 * ⛔ `null`, NOT AN EMPTY STRING. An empty string appended as a row would add a line to every
 * export, which is precisely the "no withheld cells ⇒ byte-identical" property this must keep.
 */
export function csvWithheldNote(present: readonly CsvWithheldClass[]): string | null {
  const listed = CSV_WITHHELD_CLASSES.filter((c) => present.includes(c))
  if (listed.length === 0) return null
  return [
    CSV_WITHHELD_NOTE.lead,
    ...listed.map((c) => CSV_WITHHELD_NOTE.clause[c]),
    CSV_WITHHELD_NOTE.trailer,
  ].join(" ")
}

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

// ── NF-INJ1-C: the stat line we WITHHOLD from a member who has paid for it ──────────────────────
//
// ⭐ A DIFFERENT REFUSAL FROM THE LOCK ABOVE, AND THE COPY MUST NOT BLUR THE TWO. The lock says
// "this is behind a membership"; this says "you have paid for this and we are still not showing it,
// because the number is not one we are willing to stand behind". Rendering the lock's wording here
// would sell a subscriber something they already have; rendering this wording on an unentitled row
// would describe a defect where there is none.
//
// WHAT IS ACTUALLY WRONG (NF-INJ1 §2, measured on the live board). NF1.5's ordering step hands a
// player a different player's point level and rescales the twelve stat columns to reach it, while
// his expected games stay where they were — so ~10 rows carry a per-game rate no NFL player has
// ever posted (one at 82.7 pass attempts per game against an all-time maximum of 45.4). The point
// and the games are each defensible; their RATIO is not. So the ratio is what we refuse to print.
//
// ⛔ NO FORECAST LANGUAGE, and none is possible here: this says nothing about the player, his
// health, his role or his season. It is a statement about OUR line for him. `best_alpha = 0`.
//
// ⚠️⚠️ THE SHORT LABEL NAMES THE ACTUAL CONDITION, AND THE WORDING IT REPLACED CLAIMED THE
// OPPOSITE (PM ruling, 2026-08-23, recorded in `nf-inj1-c.yaml` closeout RULINGS Decision 2).
//
// NF-INJ1-C shipped with the PM's default treatment verbatim: "stat detail withheld —
// availability-adjusted". That phrase is not merely vague, it is INVERTED — it says we adjusted
// this line for availability, when the line is withheld PRECISELY BECAUSE it was not rescaled with
// the games. The decoupling is the NF1.5 defect itself (`_RAW_SCALE_COLS` rescales the twelve stat
// columns and not `proj_games`), so the retired label described the one thing that did not happen.
//
// The replacement states the condition a reader can check for themselves — the line and the games
// disagree — and makes no claim about the player, his health or his season. ⛔ It must keep naming
// the DISAGREEMENT; a future trim back to a bare "withheld" loses the only part that says why, and
// a trim toward any availability verb re-imports the inversion.
//
// The sentence below is ADDITIVE detail in the same disclosure, not a replacement: a reader who
// taps deserves to know that the total and the games figure beside it are unaffected, which the
// short label alone cannot say. It is unchanged by the ruling.

export const STAT_LINE_WITHHELD_LABEL = "stat detail withheld — inconsistent with projected games"

/** The accessible name for the withheld cell. Read out instead of a bare em-dash, which a screen
 *  reader announces as nothing at all — i.e. as an empty cell, the one reading this exists to
 *  prevent. */
export const STAT_LINE_WITHHELD_SR_LABEL = "Stat detail withheld"

export const STAT_LINE_WITHHELD_DETAIL =
  "We hold this player's projected games and his projected stat line to each other, and for this player the two do not agree — the line implies a per-game workload no NFL player has recorded. Rather than print a number we would not stand behind, we withhold the stat detail here. His projected points and projected games are unchanged and still shown."

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

/** NF-DTB-1 — the SERVER'S refusal, met after the form was already filled in.
 *
 *  ⭐ A SECOND CONSTANT RATHER THAN A REUSE OF `LEAGUE_QUOTA_REACHED_DETAIL`, because the two states
 *  are read at different moments and one of them has to answer a question the other never raises:
 *  "did my work just disappear?". The at-the-control notice is preventative — nothing has been
 *  attempted. This one fires AFTER a save round-trip, so it has to say that nothing was stored and
 *  that the settings on screen are still there. Reusing the preventative wording here would leave a
 *  user who just pressed Save unable to tell a limit from a lost form (E8.6's shape).
 *
 *  ⚠️ It is reachable even though the control is disabled at the cap: that check reads a CACHED
 *  league list which is empty while loading and on error (`isLeagueQuotaRefusal`). */
export const LEAGUE_QUOTA_REFUSED_DETAIL =
  "Nothing was saved and your settings are still on screen. A free account keeps one personalized league, and this would have been a second one — edit or replace the league you already have, or become a member to keep several."

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

// ══ NF-K1 — WHY A ROSTER ROW HAS NO PROJECTION BESIDE IT ════════════════════════════════════════
//
// 🔴 THE ONE-WORD ANSWER COST TWO INVESTIGATIONS. Every unmatched row rendered the same "not
// matched", and on 2026-08-16 the published board carried ZERO K and ZERO D/ST — so every rostered
// kicker and defence wore wording that describes a NAME-RESOLUTION failure, pointing the reader
// (and two sessions of debugging) straight at the NF-C6P3 D/ST franchise join. That join was
// correct throughout; it simply had nothing to match against. One phrase was doing three jobs:
//
//   not-published  we did not ship that position on this board — OUR gap, nothing could have
//                  matched, and no re-import will help. Only claimable when the server tells us
//                  which positions the board carries (`board_positions`).
//   unresolved     the position IS on the board and this particular name missed — the one case
//                  where re-importing genuinely helps.
//   not-projected  a position we do not project at all (IDP, punters, coaches). Working as
//                  intended, and nothing for the reader to do.
//   unknown        we cannot tell which of the above it is (an older API that sends no
//                  `board_positions`, or a read the server could not make). Falls back to the
//                  original wording — ⛔ a confident wrong cause is worse than an unspecific one,
//                  which is exactly what "not matched" was on every kicker for a day.
//
// ⛔ NO CELL PROMISES A FIX IT CANNOT DELIVER. "Re-import" appears ONLY under `unresolved`; telling
// a user to re-import a roster whose position we never published sends them round a loop that
// cannot terminate.

/** The four causes a roster row can have no projection for. */
export type UnmatchedCause = "not-published" | "unresolved" | "not-projected" | "unknown"

/** The short in-table label. Kept to a few words — it sits in a narrow numeric column beside the
 *  points, and the full sentence lives in the tooltip/footnote below. */
export const UNMATCHED_LABEL: Record<UnmatchedCause, string> = {
  "not-published": "not published",
  unresolved: "name not matched",
  "not-projected": "not projected",
  unknown: "not matched",
}

/** The explanation, one per cause. Rendered as the cell's title and in the per-card footnote. */
export const UNMATCHED_DETAIL: Record<UnmatchedCause, string> = {
  "not-published":
    "We have not published a projection for this position on the current board, so there was nothing for this player to match against. This is a gap on our side, not a problem with your roster — re-importing will not change it.",
  unresolved:
    "We publish this position, but we could not match this particular name to a player on our board. Re-importing the league usually fixes it.",
  "not-projected":
    "We do not project this position, so there is no number to show. Your roster is fine; this slot is simply outside what we cover.",
  unknown:
    "We could not match this player to our board — either a name we could not resolve, or a player we do not project.",
}

/** The per-card footnote, assembled from the causes actually present on THIS roster.
 *
 *  ⚠️ It names the POSITIONS in the not-published case. "We have not published kickers" is
 *  actionable reading; "some players are unmatched" is the sentence that hid a two-position outage
 *  for a day. */
export function unmatchedFootnote(
  matched: number,
  total: number,
  causes: { cause: UnmatchedCause; positions: string[] }[],
): string {
  const head = `${matched} of ${total} rostered players matched to a season projection.`
  const parts = causes.map(({ cause, positions }) => {
    const posList = positions.filter(Boolean).join(" and ")
    if (cause === "not-published") {
      return posList
        ? `We have not published ${posList} projections on the current board, so those slots could not match — that gap is ours, and re-importing will not fill it.`
        : "Some positions are not on the current board, so those slots could not match."
    }
    if (cause === "unresolved") {
      return "Some names did not resolve to a player on our board — re-importing the league usually fixes those."
    }
    if (cause === "not-projected") {
      return posList
        ? `We do not project ${posList}, so those slots have no number.`
        : "Some slots are positions we do not project."
    }
    return "The rest are shown without one (a name we could not resolve, or a player we do not project)."
  })
  return [head, ...parts].join(" ")
}
