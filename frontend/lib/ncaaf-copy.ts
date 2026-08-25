// NCAAF-P3.2 — every claim-bearing string the college-football prediction surface renders.
//
// ══ WHY THESE LIVE IN ONE MODULE ══════════════════════════════════════════════════════════════
//
// The same reason `fantasy-claim-copy.ts` exists, and a sharper one here. This surface puts OUR
// number beside THE MARKET'S number, which is the single most tempting place in the product to
// write a stronger sentence — the spec's own overlap check names it: "'best bets' language is
// banned; this surface is the highest-risk place for it to creep in via copy reuse from MLB
// components". A string inlined in a component is a string no screening has ever looked at, so
// every one of them is here and `betting_ml/tests/test_ncaaf_p3_2_copy.py` runs the SAME denylist
// the track-record export runs (`export_track_record_json._CLAIM_DENYLIST`, a superset of the
// governance gates' list) over this file's literals.
//
// ══ WHAT THE EVIDENCE ACTUALLY SUPPORTS ═══════════════════════════════════════════════════════
//
// `best_alpha = 0`. VAL1 came back ALL_BUCKETS_NULL — ATS 0.496 against the close, indistinguishable
// from the placebo, and the pooled CLV null stands. So there is no measured advantage over a
// market price, and a sentence implying one would be asserting something the program has MEASURED
// to be absent. That is not caution, it is the recorded verdict.
//
// What IS supported, and what this copy therefore says: the model never sees a betting line, it
// produces a probability and a distribution, and both are shown with their uncertainty attached.
//
// ══ THREE RULES, AND THEY ARE NOT STYLE PREFERENCES ═══════════════════════════════════════════
//
// 1. ⛔ NO MEASURED FIGURE IN THIS FILE. Every number a reader sees is read off the payload (the
//    probability, the interval bounds, the band's own levels, the market line). A figure typed
//    into a component cannot be reconciled against the measurement it came from and drifts
//    silently the first time the model is re-scored (E9.56b/NF-D3). Guarded.
//
// 2. ⛔ NO NEGATED OVERCLAIM. A substring denylist is NEGATION-BLIND (NF-DS measured it: an honest
//    "not a guaranteed finish" trips the screen exactly as hard as a real guarantee), so the honest
//    sentence is the one that never contains the token at all. Hence "we make no claim to an
//    advantage over it" rather than the phrasing with the denied words inside a negation — which is
//    also, not by accident, the wording P3.1 chose for the SERVED disclosure.
//
// 3. ⭐ THE SERVED DISCLOSURE IS RENDERED VERBATIM, FROM THE PAYLOAD. It is not duplicated here.
//    `app/backend/models/ncaaf.py::DISCLOSURE` is pinned verbatim by a backend guard test so a
//    reword is a reviewed change; a second copy in this file would be free to drift from it, and
//    the drifting copy is the one the user would actually read.

/** The page's own name and standfirst. Probability + distribution language only. */
export const PAGE_TITLE = "College football projections"
export const PAGE_STANDFIRST =
  "A win probability for both teams, and the full range of scores the model thinks are plausible — not a single number pretending to be certain."

/** The label above the day picker. Deliberately "kickoff day", not "week": CFBD restarts its week
 *  numbering at 1 for the postseason, so a week label would name two different sets of games (the
 *  `season_order_week` alias landmine). The serving grain is the day, and so is the wording. */
export const DAY_PICKER_LABEL = "Kickoff day"

/** Shown when the manifest lists no published days at all — nothing has been written for the
 *  season yet. Distinct from the next string, and that distinction is the point (NF-C6b). */
export const NOTHING_PUBLISHED =
  "No projections have been published for this season yet. They go up ahead of the first slate."

/** Shown when a chosen day has no slate — the API's 404, which is the ordinary state of a Tuesday
 *  and not a fault. */
export const EMPTY_DAY =
  "No games are projected for this day. Pick another kickoff day above."

/** Shown when the read itself failed. ⚠️ MUST NOT be worded like the two above: "nothing is
 *  published" and "we could not reach the model" are different facts, and rendering them
 *  identically is what costs an investigation every time the symptom recurs. */
export const READ_FAILED =
  "We could not load the projections just now. This is a problem on our side, not an empty slate — try again in a moment."

// ══ the win-probability block ════════════════════════════════════════════════════════════════

export const WIN_PROBABILITY_LABEL = "Win probability"
/** What the number IS. Says "how often ... would win" — a frequency statement about the model's
 *  simulations, which is exactly what it is, and carries no assertion about how often the model is
 *  right. */
export const WIN_PROBABILITY_HINT =
  "How often each team wins when the model plays this game out many times. The model never sees a betting line."
/** When the payload carries no probability for a game. */
export const WIN_PROBABILITY_ABSENT = "No win probability published for this game."

// ══ the curves ═══════════════════════════════════════════════════════════════════════════════

export const MARGIN_CURVE_LABEL = "Margin"
export const TOTAL_CURVE_LABEL = "Total points"
export const MARGIN_CURVE_HINT =
  "The home team's winning margin. Left of zero is an away win. The shaded band is the middle of the range."
export const TOTAL_CURVE_HINT =
  "Both teams' points added together. The shaded band is the middle of the range."

/** ⭐ THE TOTAL AXIS BEFORE PACE ACTIVATES, and this is a MEASURED fact about the served board
 *  rather than a caution.
 *
 *  `pace_term_active` is false until a season has pace history, and without it the total's mean is
 *  driven by a league-level term that barely moves between games. Measured on the 2026 opener:
 *  the eight totals span 2.4 points against a sigma of 17.2 — about a seventh of one standard
 *  deviation — while the margins span 31.6. So the total's BAND is honest and its ordering is not:
 *  a reader comparing two games' totals early in a season is reading noise, and a surface that
 *  presented the two axes identically would be inviting exactly that.
 *
 *  ⛔ It is not an apology and it does not withdraw the number. It says which axis separates these
 *  teams — which is the margin — and leaves the total as what it is, a range. */
export const TOTAL_CURVE_HINT_NO_PACE =
  "Both teams' points added together. With no pace history yet this season, this range is close to the same for every game — read it as a range, not as a way to tell games apart. The margin is where the model separates these teams."

/** Rendered when the payload carries neither a quantile ladder nor the parameters to draw a shape.
 *  ⛔ A flat or a straight line would be a picture of a distribution we do not have; saying so is
 *  the honest render. */
export const CURVE_UNAVAILABLE = "No distribution published for this game."

/** Names the shape's provenance when the ladder is missing and only the parameters remain. Shown
 *  because a bell drawn from two parameters and a curve drawn from the model's own simulated
 *  quantiles are different pictures, and the reader is entitled to know which one they are looking
 *  at. */
export const CURVE_PARAMETRIC_NOTE =
  "Drawn from the published mean and spread — this game's simulated quantiles were not published."

// ══ the model-vs-market panel — the highest-risk copy on the surface ══════════════════════════

export const MARKET_PANEL_LABEL = "Model and market, side by side"

/** ⭐ THE FRAMING SENTENCE. It states the relationship as TRANSPARENCY and stops. It does not
 *  claim, hedge against, or hint at an advantage in either direction — because the measurement
 *  (VAL1, ALL_BUCKETS_NULL) supports no statement of that kind at all, and a hedge implying "we
 *  might have one" is the same unsupported claim in a quieter voice. */
export const MARKET_PANEL_FRAMING =
  "We publish our numbers next to the market's so you can see where they differ. We make no claim to an advantage over the market, and we publish no picks."

/** ⭐ WHAT THE PANEL SAYS WHEN THE PAYLOAD'S OWN FRAMING FLAGS NO LONGER MATCH THE ONE THIS
 *  SURFACE IS WRITTEN FOR. Withdrawing our sentence and showing the payload's own disclosure is the
 *  only honest move: the framing sentence above is warranted by `market_blind && projection_only &&
 *  best_alpha === 0` and by nothing else, so on any other payload it would be an assertion we have
 *  no basis for — and a surface that kept asserting it would be describing a model it was not
 *  written to describe. */
export const FRAMING_CHANGED =
  "The framing this projection was published under is not the one this page was written to describe, so we are showing the publisher's own wording rather than ours."

export const MODEL_COLUMN_LABEL = "Our model"
export const MARKET_COLUMN_LABEL = "Market"

/** Row labels. Each names the QUANTITY, so two numbers under one heading are the same kind of
 *  thing. */
export const ROW_HOME_MARGIN = "Home margin"
export const ROW_TOTAL = "Total points"
export const ROW_HOME_WIN = "Home win"

/** ⚠️ A price is not a belief. The book's margin is inside its implied probability, so the two
 *  percentages in that row are not directly comparable and the surface says so rather than letting
 *  the gap read as a bigger disagreement than it is. */
export const MARKET_IMPLIED_HINT =
  "Taken from the moneyline price, which includes the book's own margin — so it reads a little higher than the book's true view."

/** The market side when nothing has been captured. ⭐ NOT a blank and NOT a zero: a blank cell in
 *  a two-column comparison reads as parity, and a zero reads as a line of zero. */
export const MARKET_ABSENT_LABEL = "No market line"

/** Why there is no line, in plain words, keyed on the payload's machine-readable `reason`. The
 *  contract carries the reason precisely so a surface can say WHICH null this is; collapsing them
 *  into one sentence would throw that away at the last hop. */
export const MARKET_REASON_COPY: Record<string, string> = {
  no_line_captured_for_this_kickoff:
    "We have not captured a closing line for this kickoff yet.",
  market_read_failed:
    "We could not read the market line for this game. The projection beside it is unaffected.",
}
export const MARKET_REASON_FALLBACK = "No market line is available for this game."

// ══ a game that has already started ═══════════════════════════════════════════════════════════
//
// ⚠️ A GAP THIS SURFACE FOUND AND CAN ONLY HALF-CLOSE, said plainly because the half matters.
//
// The served payload is a PRE-KICKOFF snapshot and carries no game state and no score — that is
// `game_prediction_snapshot`'s design, not an oversight. So on the evening of a slate the cards
// would show projections for games that are underway or over, rendered identically to games that
// have not started: the single most misleading thing this surface could do on its opening day, and
// invisible to every test written before that day.
//
// What IS derivable with no contract change is whether the kickoff INSTANT has passed, and that is
// what these two strings say — no more. ⛔ They do not claim to know a score, a state or a result,
// because the payload does not carry one. The fuller fix (a live game state beside the projection)
// is a P3.1/P3.3 contract question and is recorded in the spec's closeout.

/** The chip on a card whose kickoff instant is in the past. */
export const KICKED_OFF_LABEL = "Kicked off"

/** ⭐ The sentence that stops a stale-looking card from reading as a live one. It states what the
 *  number IS — a snapshot taken before the game — rather than apologising for what it is not. */
export const KICKED_OFF_NOTE =
  "This projection was taken before kickoff and is not updated once a game starts. We do not show live scores here."

// ══ provenance + the stubbed onward links ════════════════════════════════════════════════════

export const PROVENANCE_LABEL = "How this was produced"
/** ⚠️ `pace_term_active: false` before the season starts is CORRECT by construction, not a fault:
 *  week-1 team-weeks carry no pace input and a null contributes exactly nothing to the fit. Saying
 *  so keeps a reader from reading an honest absence as a broken model. */
export const PACE_INACTIVE_NOTE =
  "The pace term contributed nothing to this projection — there is no pace history yet this season."

/** P3.3 is not built. ⛔ A link to a route that does not exist is exactly the defect the E2E suite
 *  was built to catch, so the affordance is present, labelled, and does not navigate. */
// ══ COLLAPSING A CARD ═════════════════════════════════════════════════════════════════════════
//
// A full card is tall — on a phone one matchup is more than a viewport, so an eight-game slate is
// eight scrolls before a reader has seen the slate at all. Collapsing trades the curves for a
// scannable summary.
//
// ⭐ CARDS OPEN EXPANDED. The distributional curve is what this surface IS (the P3 brand
// directive), and a first-time reader who is shown a list of percentages never learns that we
// publish distributions at all. The viewer's own choice is remembered instead, so collapsing is a
// preference a returning reader keeps rather than a default we impose.
//
// ⛔ THE COLLAPSED SUMMARY SHOWS THE BAND, NEVER A POINT. "Never a point number" is the directive
// for this axis, and a collapsed row is exactly where a single tidy number would be tempting.
//
// ⭐ THE PER-CARD CONTROL IS THE SHARED ACCORDION'S CHEVRON, so it needs no copy of its own —
// `app/props/page.tsx` already collapses per-game groups exactly this way, and a second labelled
// button for the same job would be a second interaction language for the same idea. Only the
// slate-level control is worded, because "expand all" has no glyph.

export const EXPAND_ALL_LABEL = "Expand all"
export const COLLAPSE_ALL_LABEL = "Collapse all"

/** ⚠️ THE PACE CAVEAT HAS TO SURVIVE COLLAPSE.
 *
 * With `pace_term_active` false every game's total band is nearly identical (measured on the 2026
 * opener: eight totals spanning 2.4 points against a sigma of 17.2). A collapsed slate is the view
 * that puts those eight near-identical ranges in a vertical list — i.e. the view that most invites
 * a reader to compare them — while the sentence explaining why they are alike lives on the curve
 * that collapsing just hid. So the marker rides the summary row too, short enough to fit. */
export const SUMMARY_NO_PACE_MARKER = "similar across games right now"

export const TEAM_PAGE_STUB_LABEL = "Team page coming soon"
