// E9.46 — THE CANONICAL HOME-PAGE COPY. Every claim-bearing string the positioning page renders.
//
// ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
//
// NF-TR1 put the fantasy product's claims in `fantasy-claim-copy.ts` so no surface could quietly
// write its own stronger version. The home page is the one place where BOTH verticals pitch at
// once, and the betting half had no such module — its copy lived inline in `app/page.tsx`,
// unscreened, and said "Daily edge, quantified" as the company's H1.
//
// `betting_ml/tests/test_e9_46_home_copy.py` parses THIS FILE'S string literals and runs the
// export's `_CLAIM_DENYLIST` over them, exactly as the NF-TR1 suite does for the fantasy copy. A
// sentence written inline in JSX is a sentence no denylist has ever read.
//
// ⛔ TWO RULES CARRY THE WHOLE STORY:
//
//   1. NO MEASURED NUMBER IS TYPED HERE. Every figure on the page is read from a served payload at
//      render time. A figure typed into a component cannot be reconciled against the measurement it
//      came from (the E9.56b/NF-D3 discipline).
//
//   2. NO PERFORMANCE CLAIM, IN EITHER VERTICAL. `best_alpha = 0`: the betting program has six
//      recorded no-edge results and has never demonstrated a durable advantage over the closing
//      market, and the fantasy track record's own 90% interval includes zero (NF-D17).
//
// ⭐ RULE 2 IS NOT "SAY NOTHING ABOUT THE RECORD" — and getting that distinction right is the point
// of the 2026-08-08 revision. There IS a daily model-vs-market record; it is computed every day,
// losses included, and it is a real part of the product. What has not been demonstrated is a
// durable advantage over the closing market. Copy that implied we do not measure ourselves would be
// just as false as copy claiming an edge, and it would give away the most credible thing we have.
// ⚠️ The record lives on the members' scorecard — every record endpoint (`/picks/scorecard`,
// `/performance`, `/picks/today`, `/picks/history`) returns 401 to an anonymous request, verified
// 2026-08-08. So every reference to it here says "members" and every link to it is marked as
// needing an account; ⛔ do NOT write "public record" copy unless a public route actually ships.

import { PRODUCT_HOOK, TRACK_RECORD_TRUST_LINK } from "@/lib/fantasy-claim-copy"

// ══ THE HERO ═══════════════════════════════════════════════════════════════════════════════════

/** The hero. One identity that has to hold for a visitor arriving for either product.
 *
 *  ⭐ THE HEADLINE IS ABOUT THE SHAPE OF THE ANSWER, not about outcomes. Every outcome-shaped
 *  headline available to us ("win more", "beat the book") is either forbidden outright or a claim
 *  we cannot support. "The number is only half the answer" is the product: a projection plus how
 *  sure we are plus what to do about it — which is also exactly what the two cards below show. */
export const HERO = {
  eyebrow: "Betting intelligence · Fantasy decision tools",
  headline: "The number is only half the answer.",
  subhead:
    "MLB betting intelligence and fantasy football decision tools built to show you what the models expect, how confident they are, and what to do with that information.",
} as const

/** ⚠️ MLB-SPECIFIC PRODUCT LANGUAGE, DELIBERATELY NOT THE COMPANY H1 (operator, 2026-08-08).
 *
 *  This was the site's headline until this release, from when Credence was one product. It is kept
 *  as the betting product's own tagline and is SCOPED to the MLB card — `test_e9_46_home_copy.py`
 *  asserts it never reappears in `HERO`, in the platform positioning, or in the site metadata,
 *  because the whole point of retiring it as the H1 is that it does not span a company that now
 *  ships fantasy too.
 *
 *  ⚠️ ON THE WORD "EDGE": here it names the model-vs-market DIFFERENCE the product quantifies and
 *  displays, not a demonstrated advantage — and it renders inches from the card that states plainly
 *  that no durable advantage over the closing market has been shown. That adjacency is what keeps
 *  it honest, so ⛔ do not lift this string somewhere the honest framing does not travel with it. */
export const MLB_PRODUCT_TAGLINE = "Daily edge, quantified."

// ══ THE TWO DOORS ══════════════════════════════════════════════════════════════════════════════

export type VerticalDoor = {
  key: "betting" | "fantasy"
  sport: string
  surface: string
  status: string
  headline: string
  detail: string
  cta: { label: string; href: string }
  trust: { label: string; href: string; needsAccount: boolean }
}

/** ⭐ FANTASY FIRST (operator, 2026-08-08): fantasy is the current acquisition priority, so it is
 *  the first door and the first product proof on the page. */
export const VERTICALS: readonly VerticalDoor[] = [
  {
    key: "fantasy",
    sport: "NFL",
    surface: "Fantasy",
    status: "Live for 2026",
    // ⭐ REUSED VERBATIM from the NF-TR1 canonical set rather than paraphrased. Paraphrase is how a
    // hedge gets dropped on one surface while a boast appears on another.
    headline: PRODUCT_HOOK[0].title,
    detail: PRODUCT_HOOK[0].detail,
    cta: { label: "See the free rankings", href: "/fantasy/rankings" },
    trust: {
      label: TRACK_RECORD_TRUST_LINK.label,
      href: TRACK_RECORD_TRUST_LINK.href,
      needsAccount: false,
    },
  },
  {
    key: "betting",
    sport: "MLB",
    surface: "Betting intelligence",
    status: "Live now",
    headline: "Where our model differs from the market, and by how much.",
    detail:
      "Every game, every day: our probability, the de-vigged market consensus, the gap between them, and the range around our estimate. We grade every one of them against the market afterwards — losses included.",
    cta: { label: "See today's model-vs-market read", href: "#today" },
    trust: { label: "How we grade out", href: "/performance", needsAccount: true },
  },
]

// ══ THE FANTASY PROOF ══════════════════════════════════════════════════════════════════════════

/** The public featured-player card (`/fantasy/nfl/featured-player`).
 *
 *  ⭐ WHY A REAL PLAYER AND NOT AN ILLUSTRATION: "built for your league, not a generic one" is a
 *  claim until a visitor watches one player's season total move with the scoring format, at which
 *  point it is an observation. Everything on the card is read from the served 2026 artifact.
 *
 *  ⛔ `leanCaveat` is NOT optional garnish. Measured on the live artifact: ZERO of the 111 players
 *  eligible for this card have `mktLean == "independent"`, because `independent` is precisely the
 *  thin-data rookie case that carries no drivers. So the rank gap is a real disagreement and never
 *  an independent one, and a card that showed the gap without saying so would overstate it. */
export const FANTASY_PROOF = {
  eyebrow: "A real player from this season's board",
  heading: "Built for your league, not a generic one.",
  /** ⭐ The mechanical note on HOW the player is chosen. It sits beside — never instead of —
   *  NF-TR1's `DISAGREEMENT_HOOK`, which the card renders verbatim: this section is the hook
   *  instantiated, so paraphrasing it here and dropping the canonical string would be exactly the
   *  drift `fantasy-claim-copy.ts` exists to prevent. */
  selectionNote:
    "Picked by the largest gap between our rank and where the market is drafting him — computed from the board on every page load, not hand-chosen, and not always a player we like more than the crowd does.",
  ourRankLabel: "Our rank",
  marketRankLabel: "Market rank",
  adpLabel: "ADP",
  gamesLabel: "Proj. games",
  rangeLabel: "80% range",
  formatsHeading: "The same player, scored three ways",
  formatsNote:
    "Standard, half-PPR and full-PPR are the same projection under three sets of league rules. Import your league and every number on the board is recomputed for your actual scoring, your roster slots and your team count.",
  driversHeading: "What is moving this projection",
  driversNote:
    "Points added or removed against a positional baseline, from the model that sets the level. These are the three largest; the rest are on the player page.",
  gamesNote:
    "Our points are an expected season total — the chance he misses games is already priced in, which is why projected games sits beside it.",
  cta: { label: "See the free rankings", href: "/fantasy/rankings" },
  secondaryCta: { label: "Customize for your league", href: "/subscribe" },
  /** Shown when the read fails or nothing qualifies. The section hides rather than rendering a
   *  broken card — but never silently: this is the honest line if it ever needs to be shown. */
  unavailable:
    "This season's featured player could not be loaded just now. The full board is on the rankings page.",
} as const

// ══ THE MLB PROOF ══════════════════════════════════════════════════════════════════════════════

/** ⚠️⚠️ THIS COPY IS DOWNSTREAM OF A SQL ORDER BY, AND IT HAS ALREADY BEEN WRONG ONCE.
 *
 *  The first E9.46 cut said "today's widest model-vs-market gap". That was false at the time — the
 *  serving query ordered `game_datetime ASC`, i.e. the earliest-starting qualifying game, and
 *  nothing in the selection looked at the gap. The operator's fix (2026-08-08) was to change the
 *  QUERY rather than the copy, so the description below is now true by construction:
 *
 *    eligibility  `layer4_h2h_conviction_flag = TRUE`
 *    ordering     `_FEATURED_ORDER_BY` — largest `|our probability − market consensus|` first
 *
 *  ⇒ if that ORDER BY ever changes again, THIS STRING IS WRONG THE SAME DAY. It is pinned against
 *  the SQL by `test_e9_46_featured_selection.py::test_the_home_copy_describes_the_actual_order_by`.
 *
 *  ⭐ THE FLAG IS NOT A MARKET MEASUREMENT, and it is doing more work now than it was. It is
 *  `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02` (`scripts/predict_today.py`) — two INDEPENDENT
 *  Credence estimators agreeing with EACH OTHER, computed with no reference to odds at all. That is
 *  why the badge reads "our models agree": it is what was measured. ("High conviction" invites a
 *  bettor to read it as confidence in the result; "high model disagreement" is the exact inverse of
 *  the truth.) Once the sort key became the gap, the flag also became the guard on a MAXIMUM ORDER
 *  STATISTIC — see the note on `gapHint`, which is where that honesty lands in front of a visitor.
 *
 *  📊 MEASURED, AND WORTH KNOWING BEFORE EDITING ANY OF THIS (2026-07-01 → 08-07, 34 slates): the
 *  gap now selects a TOTALS pick on 31 of 34 days, because the totals model's eligible gaps are
 *  structurally ~3× wider than the moneyline's (median 0.116 vs 0.036) — a difference in the scale
 *  of the two markets, not in how much we disagree. So this card is in practice a totals card. If
 *  that is not wanted, the fix is in the ORDER BY (rank within market type), not here. */
export const MLB_PROOF = {
  eyebrow: "Today's featured model-vs-market read",
  /** ⚠️ "usually alternating", NOT "alternating". `market_pref` is a SORT KEY, not a filter — on a
   *  day when the market whose turn it is has no qualifying game, the other one is featured rather
   *  than showing nothing. Promising strict alternation would be a claim the SQL does not make and
   *  a visitor could catch us on. It is also why the card labels the market outright instead of
   *  letting the reader infer it from the day. Pinned by `test_e9_46_featured_selection.py`. */
  frame:
    "A demonstration, not a recommendation. We look at the games where our two independent models land in close agreement with each other, and feature the one where our number sits furthest from the market's — on the moneyline or on the total, usually alternating between them so you see both. Whichever it is, it says so. You get our probability, the market's, the distance between them, and the range around our estimate.",
  empty:
    "Nothing to show yet. The morning run publishes after roughly 9am ET and re-scores once lineups are confirmed, and until it does we leave the previous read up. Some days no game qualifies at all, which is a real answer rather than a gap in the page.",
  unavailable:
    "Today's read could not be loaded just now. Nothing is wrong with the model — this is the page failing to reach it. Try again shortly, or open the daily card.",
  /** ⭐ Shown on a CARRIED-OVER card (`is_stale`). It has to say three things a visitor would
   *  otherwise get wrong: that this is not today's slate, which day it IS (the date renders right
   *  above it), and that nothing is broken. The card is deliberately left up rather than blanked —
   *  operator, 2026-08-08 — so the section is never empty between the day rolling over and the
   *  morning run publishing. */
  staleNote:
    "Today's run hasn't published yet, so this is the most recent read we've posted — for the date shown above, not today's slate. It stays up until the new numbers land.",
  preliminaryNote: "Preliminary — lineups are not confirmed yet.",
  /** ⚠️ "Gap", never "Edge". The served field is called `edge` and the signed-in surfaces render it
   *  that way; on a marketing page "edge" reads as a claim to have one. */
  labels: {
    model: "Our model",
    market: "Market consensus",
    gap: "Gap",
    range: "80% range",
  },
  /** ⭐ THE MARKET, NAMED IN FULL. The card alternates between two markets that quote completely
   *  different things — a win probability and a runs total — so "48.9%" means something different
   *  depending on which one you are looking at. These render as a badge on the card rather than as
   *  a small eyebrow, and `marketHint` is the one-line answer to "what am I looking at". */
  markets: {
    h2h: { label: "Moneyline", hint: "Who wins the game. Our number is the chance the side we lean on wins outright." },
    totals: { label: "Total runs", hint: "How many runs both teams combine for. Our number is the chance the game goes over the posted line." },
  },
  /** ⭐⭐ THE SECOND SENTENCE IS THE PRICE OF SORTING ON THIS NUMBER, and it is not optional.
   *  Featuring the day's LARGEST gap is a maximum order statistic: across a slate, the extreme
   *  value is the one most likely to be produced by something wrong on our side — a stale starter,
   *  a thin market, one model mis-firing — rather than by a market that has genuinely mispriced a
   *  game. Six recorded no-edge results say we have not shown we can tell those apart. A big green
   *  number with no such caveat reads as an opportunity, which is the one thing this card must not
   *  claim to be. Pinned by `test_e9_46_home_copy.py`. */
  gapHint:
    "The distance between our probability and the market's de-vigged consensus probability. It measures disagreement, not advantage — and because we feature the largest one on the board, it is also the read most likely to be ours getting something wrong rather than the market's.",
  /** The badge, and the popover that stops it being read as a promise about the result. */
  agreementBadge: "Our models agree",
  agreementHint:
    "Two independent Credence models — one estimating the win probability directly, the other from the projected run differential — land within two points of each other on this game. It is a statement about our own models, computed without looking at the odds, and it says nothing about whether the market is wrong.",
  yesterdayLabel: "Yesterday's featured read",
  /** ⭐ THE RECORD SENTENCE. It has to do two things at once: not claim an edge, and not pretend we
   *  fail to measure one. Both halves are load-bearing — see the module header. */
  recordNote:
    "Every featured read is graded against the market afterwards, wins and losses alike, and the full daily record is on the members' scorecard. What that record has not shown is a durable advantage over the closing market, and we would rather say so here than let the card imply otherwise.",
  fullCard: { label: "See the full daily card", href: "/dashboard", needsAccount: true },
} as const

// ══ THE METHODOLOGY / TRUST SECTION ════════════════════════════════════════════════════════════

/** ⭐ THE POSITIONING MOVED HERE FROM THE HERO (operator, 2026-08-08), and it belongs here because
 *  the four principles below are its PROOF — the statement and its evidence in one block, rather
 *  than a claim at the top of the page and its justification three screens down.
 *
 *  ⛔ NOTHING ABOUT SYNTHETIC VALIDATION / SIM-V1 GOES HERE until that capability is operational.
 *  Advertising roadmap work as a shipped capability is the same defect class as a "coming soon"
 *  link into a route that does not exist, on the one section whose subject is our standard of
 *  evidence. When it ships, "we stress-test the models and the gates themselves" is a fifth cell. */
export const METHOD = {
  heading: "Sports models that admit what they don't know.",
  intro:
    "That is a standard of evidence, not a slogan, so here is what it commits us to. Each of these is something you can check on the site rather than take on trust.",
} as const

export const PRINCIPLES: readonly { title: string; detail: string }[] = [
  {
    title: "We show the uncertainty",
    detail:
      "Every projection ships with an 80% range and every game probability with a credible interval. A wide one means we genuinely do not know, and we would rather show that than round it into a confident-sounding number.",
  },
  {
    title: "We grade ourselves in public",
    detail:
      "Every MLB pick is scored against the market consensus after the game, and every past fantasy season is scored against what actually happened — one row per player, wins and losses both, over the whole set rather than a chosen subset.",
  },
  {
    title: "We show our inputs",
    detail:
      "The factors moving a projection or a probability are on the page, with what each one added or removed. You can disagree with us and see exactly where.",
  },
  {
    title: "We retire what fails",
    detail:
      "A model that does not clear the gates we set for it before we looked at the answer gets closed out, in the changelog, with the reason. Several have been.",
  },
]

// ══ THE SEASON ROADMAP ═════════════════════════════════════════════════════════════════════════

/** ⛔ A `live: false` row renders as TEXT and must never carry a link — E9.56c's dead `/pricing`
 *  CTA wearing a friendlier label. When NCAAF and NFL betting intelligence ship, flip `live` and
 *  add the href in the same change.
 *
 *  ⚠️ NO DATES (operator, 2026-08-08). "Coming this season" is a commitment we control; "around
 *  Aug 29" is a promise a visitor can check and find false on the day. */
export const SEASON_ROADMAP: readonly {
  sport: string
  what: string
  when: string
  live: boolean
}[] = [
  { sport: "MLB", what: "Betting intelligence", when: "Live", live: true },
  { sport: "NFL", what: "Fantasy rankings and decision tools", when: "Live for the 2026 season", live: true },
  { sport: "NCAAF", what: "Betting intelligence", when: "Coming this season", live: false },
  { sport: "NFL", what: "Betting intelligence", when: "Coming this season", live: false },
]

export const ROADMAP_HEADING = "What is live, and what is next"

/** ⭐ The sentence that keeps the roadmap from becoming a promise of picks. Both un-shipped rows are
 *  the SAME product as the MLB one — model-vs-market analysis with the uncertainty shown — not a
 *  different, better one that wins. Neither has cleared a live betting gate; the NCAAF closing-line
 *  result is a recorded null. */
export const ROADMAP_NOTE =
  "The two that are coming are the same product as the MLB one: model projections, the market's number beside them, and the record kept in the open. They are analysis rather than an assurance of results — no model here has demonstrated a durable advantage over the closing market, and we will say so plainly on the day one does."

// ══ THE CLOSING SECTION ════════════════════════════════════════════════════════════════════════

export const FOOTER_CTA = {
  headline: "Start with the free half.",
  detail:
    "The NFL rankings and the full fantasy track record are open to anyone, no account required. A membership adds the daily MLB card and its scorecard, and the draft, trade, waiver and start/sit calls in your league's own scoring.",
  disclaimer:
    "Everything here is analysis, published for information only. It is not financial advice, and you are solely responsible for any wager you choose to place.",
} as const

// ══ THE LANDING FAQ ════════════════════════════════════════════════════════════════════════════
//
// ⚠️ MOVED HERE FROM `components/landing-faq.tsx` BY E9.46, and not for tidiness. Inline in JSX it
// was seven paragraphs of claim-bearing prose no denylist had ever read — and it had gone FALSE:
// it answered "what sports does Credence cover?" with "MLB baseball only, for the 2026 season" and
// called the company "a baseball analytics tool", on the page now selling an NFL fantasy product.
//
// ⭐ THE ANSWERS GET PROGRESSIVELY MORE TECHNICAL, and repetition is a bug here (operator,
// 2026-08-08): the first cut said "every number ships with a range" in four different answers,
// which reads as a script rather than an explanation. Each answer now adds something the one above
// it did not.
//
// ⛔ TWO FACTUAL POINTS THAT WERE WRONG BEFORE THIS REVISION AND MUST STAY RIGHT:
//   · The MLB comparison is a de-vigged MARKET CONSENSUS, not one designated sportsbook. Verified
//     against `dbt/models/mart/mart_odds_consensus.sql`: each book's two-way prices are converted
//     to implied probabilities and normalised to sum to one (that is the de-vig), then consensus is
//     a PLAIN UNWEIGHTED `avg()` across every book that priced both sides before first pitch. There
//     is a sharp/soft split in that model, but `home_win_prob_consensus` — the column the pick is
//     scored against — does not use it. ⛔ Do not write "weighted toward sharp books"; it is not.
//   · Bovada is where a pick's PRICE is shown and graded, which is a different thing from the
//     probability we compare against. Both facts belong in the answer; conflating them is what the
//     previous wording did.

export const LANDING_FAQ: readonly { q: string; a: string }[] = [
  {
    q: "What does Credence actually do?",
    a: "Two products, one method. For MLB we publish a daily card comparing our model's probability for every game against the market's, with the reasoning and the uncertainty attached, and we grade each one after the fact. For the NFL we publish fantasy projections and rankings recomputed for your league's own scoring, plus the draft, trade, waiver and start/sit calls that follow from them. Both are analysis tools. Neither is a picks service, and nothing is ever wagered or submitted on your behalf.",
  },
  {
    q: "Does Credence claim to beat the betting market?",
    a: "No — and the distinction matters more than the answer. We do measure it: every MLB pick is scored against the market after the game, wins and losses, and that daily record is part of the product rather than something we keep quiet about. What the record has not shown is a durable advantage over the closing market. Publishing where our model disagrees with the market, and how those disagreements turned out, is a different and far more defensible thing than claiming those disagreements can be reliably converted into returns, and we are only willing to do the first.",
  },
  {
    q: "What market are the MLB numbers compared against?",
    a: "A de-vigged market consensus, not one designated sportsbook. For each game we take every book that priced both sides before first pitch, convert its two-way prices into implied probabilities, and normalise them to sum to one — that removes the book's built-in margin, which is what makes the number comparable to a model probability at all. The consensus is then a straight average across those books, with none weighted above another. Separately, where a card shows a price you could actually take, that price is Bovada's; the comparison probability and the quoted price are two different things.",
  },
  {
    q: "What is the difference between the model number and the market number?",
    a: "The model number is the probability our model assigns to an outcome from the game's own inputs — pitching, offense, bullpen, park and run environment. The market number is what the consensus price implies once the margin is stripped out. The gap between them is disagreement, and that is all it is: it locates where our read and the market's part company, which is not the same as establishing that one of them is right. A large gap is a reason to look closer, not evidence of a mispricing.",
  },
  {
    q: "Why does everything come with a range?",
    a: "Because a single number hides the thing you most need in order to act on it. Our models are Bayesian: they estimate a distribution rather than a point, so alongside every projection we can say how much of its spread is real uncertainty. That is why a fantasy projection ships with an 80% band and a game probability with a credible interval — and why a wide one is informative rather than embarrassing. It tells you which calls are close enough that reasonable people should disagree, and which are not.",
  },
  {
    q: "Is any of this automated betting?",
    a: "No. Automated placement is not possible in the US market, and we would not build it if it were. Every wager is your own manual decision, made on your own account; Credence never places, submits or sizes a bet for you.",
  },
  {
    q: "What is free, and what does a membership cover?",
    a: "The NFL rankings and projections are readable without an account, as is the full fantasy track record going back to 2019. A membership adds the daily MLB card with its scorecard and research surfaces, and on the fantasy side the decision support — draft board, trade and waiver calls, and start/sit, all computed in your league's scoring rather than a generic one.",
  },
]
