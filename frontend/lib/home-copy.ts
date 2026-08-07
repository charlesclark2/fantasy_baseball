// E9.46 — THE CANONICAL HOME-PAGE COPY. Every claim-bearing string the positioning page renders.
//
// ══ WHY THIS FILE EXISTS AT ALL ════════════════════════════════════════════════════════════════
//
// NF-TR1 put the fantasy product's claims in `fantasy-claim-copy.ts` so no surface could quietly
// write its own stronger version. The home page then became the one place in the product where
// BOTH verticals make a pitch at the same time — and the betting half had no such module: its
// copy lived inline in `app/page.tsx`, unscreened, and said "Daily edge, quantified".
//
// So this is the betting-side and platform-side twin of that file, and it exists for the same
// mechanical reason: `betting_ml/tests/test_e9_46_home_copy.py` parses THIS FILE'S string literals
// and runs the export's `_CLAIM_DENYLIST` over them, exactly as the NF-TR1 suite does for the
// fantasy copy. A sentence written inline in JSX is a sentence no denylist has ever read.
//
// ⛔ NOT HERE, and these are the two rules that carry the whole story:
//
//   1. NO MEASURED NUMBER. Not a win rate, not an ROI, not a record, not a count of picks. Every
//      figure on this page is READ FROM A SERVED PAYLOAD at render time (the pick-of-the-day's
//      probabilities) or is not shown at all. A figure typed into a component cannot be reconciled
//      against the measurement it came from — the E9.56b/NF-D3 discipline.
//
//   2. NO PERFORMANCE CLAIM, IN EITHER VERTICAL. `best_alpha = 0`: the betting program has six
//      recorded no-edge results and has never demonstrated a market edge, and the fantasy track
//      record's own 90% interval includes zero (NF-D17). So neither half of this page may claim
//      one. What both halves DO claim is the thing that is actually true and actually rare:
//      the model's read, the market's, the distance between them, the uncertainty around it, and
//      a record published with the losses in it.
//
// ══ THE FRAME FOR THE PICK OF THE DAY, WHICH IS THE RISKIEST BLOCK ON THE PAGE ═════════════════
//
// A "pick of the day" on a marketing home page is one word away from being a tout, and a tout is
// precisely the edge claim `best_alpha = 0` forbids. The operator's decision (2026-08-07) is that
// it ships as a DEMONSTRATION, not a recommendation: it is the game where our model's probability
// sits furthest from the market's price today, shown with its uncertainty and with yesterday's
// graded result — win or loss — beside it. That is a product demo of "we show our work", and it
// is honest. "Bet this" is not, and no amount of hedging afterwards would make it so.
//
// ⭐ THE OTHER HALF OF THAT DECISION, and it is a CODE rule rather than a copy one: this page
// renders the served pick's NUMBERS and this file's own STATIC labels. It deliberately does NOT
// render `ai_summary` or `model_narrative`. Those are model-generated prose, they are written for
// the signed-in analysis surfaces, and today they use "edge" freely ("a +3.2pp edge over the
// Bovada closing line" — verbatim from the live payload). Rendering server prose on a marketing
// page would put un-screenable, un-versioned copy on the one surface where the claim discipline is
// strictest, and the denylist scan in `home-positioning.spec.ts` would then be asserting against a
// string this repo does not control. See `components/home/pick-of-the-day.tsx`.

import { PRODUCT_HOOK, TRACK_RECORD_TRUST_LINK } from "@/lib/fantasy-claim-copy"

// ══ THE PLATFORM ═══════════════════════════════════════════════════════════════════════════════

/** The hero. One identity that has to hold for a visitor arriving for either product.
 *
 *  ⚠️ The headline is deliberately about METHOD, not about outcomes. Every outcome-shaped headline
 *  available to us ("win more", "find value", "beat the book") is either forbidden outright or is a
 *  claim we cannot support — so the honest headline is the one thing that is unambiguously true
 *  about the product and unusual in the category. */
export const HERO = {
  eyebrow: "MLB betting intelligence · NFL fantasy",
  headline: "Sports models that admit what they don't know.",
  subhead:
    "Credence builds transparent, model-driven analysis across two products — betting intelligence for MLB and fantasy rankings for the NFL. Every number ships with the uncertainty around it, and we grade ourselves in public.",
} as const

/** The through-line. What makes the two verticals one company rather than two side projects.
 *
 *  ⚠️ Every one of these is a statement about PROCESS that a reader can immediately verify on the
 *  site — the ranges are on the projections, the losses are in the record, the drivers are on the
 *  pick, the retired models are in the changelog. A pillar a visitor cannot check is a slogan. */
export const PRINCIPLES: readonly { title: string; detail: string }[] = [
  {
    title: "We show the uncertainty",
    detail:
      "Every estimate carries a range. A wide one means we genuinely do not know, and we would rather say so than round it off into a confident-sounding number.",
  },
  {
    title: "We grade ourselves in public",
    detail:
      "The record is computed over the whole set, losses included — not a curated selection of the days that went well.",
  },
  {
    title: "We show our inputs",
    detail:
      "The factors driving a projection or a probability are on the page. You can disagree with us and see exactly where.",
  },
  {
    title: "We retire what fails",
    detail:
      "A model that does not clear the gates we set for it before we looked at the answer gets closed out, in the changelog, with the reason.",
  },
]

// ══ THE TWO DOORS ══════════════════════════════════════════════════════════════════════════════

/** A vertical's card. `trust` is the honest-record link; `trustNeedsAccount` is what keeps that
 *  link from being a small lie.
 *
 *  ⭐ THE ASYMMETRY IS REAL AND IS STATED RATHER THAN HIDDEN. The fantasy record
 *  (`/fantasy/track-record`) is genuinely public — no account, every season, one row per player.
 *  The MLB scorecard (`/performance`) is behind the auth guard, because it has always been a
 *  subscriber surface and E9.46 is a frontend story that may not stand up a new public endpoint.
 *  Labelling both "see the record" would send a stranger to a login wall from a trust link, which
 *  is the one place a product cannot afford to surprise someone. So the MLB card says so, and the
 *  public proof it offers instead is the one on this very page: the pick-of-the-day carries
 *  yesterday's graded result, win or loss, to anyone who loads the page. */
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

export const VERTICALS: readonly VerticalDoor[] = [
  {
    key: "betting",
    sport: "MLB",
    surface: "Betting intelligence",
    status: "Live now",
    headline: "Where our model disagrees with the market, and by how much.",
    detail:
      "A daily card across every slate: our probability, the price the market is offering, the distance between them, and the range around our estimate. The reasoning behind each one is on the page — and so is how it turned out.",
    cta: { label: "See today's model-vs-market read", href: "#today" },
    trust: { label: "How we have graded out", href: "/performance", needsAccount: true },
  },
  {
    key: "fantasy",
    sport: "NFL",
    surface: "Fantasy",
    status: "Launching now",
    // ⭐ REUSED VERBATIM from the NF-TR1 canonical set rather than paraphrased. Paraphrase is
    // exactly how a hedge gets dropped on one surface while a boast appears on another, which is
    // the failure `fantasy-claim-copy.ts` was created to prevent; the home page is a THIRD surface
    // making the same pitch, so it inherits the same words.
    headline: PRODUCT_HOOK[0].title,
    detail: PRODUCT_HOOK[0].detail,
    cta: { label: "See the free rankings", href: "/fantasy/rankings" },
    trust: {
      label: TRACK_RECORD_TRUST_LINK.label,
      href: TRACK_RECORD_TRUST_LINK.href,
      needsAccount: false,
    },
  },
]

// ══ THE PICK OF THE DAY ════════════════════════════════════════════════════════════════════════

/** The framing that turns a featured pick into a transparency feature.
 *
 *  ⛔ `frame` is load-bearing and is NOT decoration. Without it this block is a tout — the single
 *  most damaging thing this page could ship, because it would contradict `best_alpha = 0` on the
 *  company's own front door. Do not trim it for length, and do not move it below the numbers: a
 *  visitor reads the big number first, so the framing has to arrive with it. */
export const PICK_OF_THE_DAY = {
  eyebrow: "Today's widest model-vs-market gap",
  frame:
    "This is a demonstration, not a recommendation. Of today's games, this is the one where our model's probability sits furthest from the market's implied price. We show both numbers, the gap, and the range around our estimate — then we publish how it went, win or lose.",
  /** The honest empty state. ⭐ It is a REAL ANSWER, not an apology: on plenty of days nothing in
   *  the slate clears the model's own threshold, and manufacturing something to fill the card is
   *  the exact behaviour this product exists not to have. */
  empty:
    "Nothing to show yet for today. The morning run publishes after roughly 9am ET, and it re-scores once lineups are confirmed. Some days it surfaces nothing at all, which is a real answer rather than a gap in the page.",
  /** Shown when the read itself failed — distinct from "the model published nothing", because
   *  those are different facts and a page that conflates them is lying about one of them. */
  unavailable:
    "Today's read could not be loaded just now. Nothing is wrong with the model — this is the page failing to reach it. Try again shortly, or open the daily card.",
  staleNote:
    "Today's analysis is still processing — this is the most recent published read. New numbers arrive after lineup confirmation.",
  preliminaryNote: "Preliminary — lineups are not confirmed yet.",
  /** Column labels. ⚠️ "Gap" and not "Edge": the served field is called `edge` and the signed-in
   *  surfaces render it that way, but on a marketing page "edge" reads as a claim to have one, and
   *  we do not have one to claim. The quantity is a DIFFERENCE between two probabilities; naming
   *  it that costs nothing and is what it actually is. */
  labels: {
    model: "Our model",
    market: "Market",
    gap: "Gap",
    range: "80% range",
  },
  gapHint:
    "The distance between our probability and the market's implied probability. It measures disagreement, not advantage.",
  yesterdayLabel: "Yesterday's featured read",
  fullCard: { label: "See the full daily card", href: "/dashboard", needsAccount: true },
} as const

// ══ THE SEASON ROADMAP ═════════════════════════════════════════════════════════════════════════

/** What is live, what is landing, and what is honestly still ahead.
 *
 *  ⛔ A DATE HERE IS A PROMISE A STRANGER CAN CHECK. `live: false` rows render as teasers and must
 *  NOT link anywhere — E9.56c's dead `/pricing` CTA killed the buy path, and a "coming soon" link
 *  into a route that does not exist is the same defect wearing a friendlier label. When NCAAF and
 *  the NFL game model ship, flip `live` and add the href in the same change. */
export const SEASON_ROADMAP: readonly {
  sport: string
  what: string
  when: string
  live: boolean
}[] = [
  { sport: "MLB", what: "Betting intelligence — daily model-vs-market analysis", when: "Live", live: true },
  { sport: "NFL", what: "Fantasy rankings and draft support", when: "Live for the 2026 season", live: true },
  { sport: "NCAAF", what: "Game analytics", when: "Around Aug 29", live: false },
  { sport: "NFL", what: "Game model", when: "Around Sep 9", live: false },
]

/** ⭐ The sentence that keeps the roadmap from becoming a promise of picks. Both un-shipped rows
 *  are ANALYTICS: projections and model-vs-market transparency. Neither has cleared a live betting
 *  gate — the NCAAF closing-line result is a recorded null — so a teaser implying otherwise would
 *  be selling a result we do not have. */
export const ROADMAP_NOTE =
  "Coming-soon means model projections and the same model-vs-market transparency you can see on the MLB card today. It does not mean picks we say will win — no model here has demonstrated an advantage over the closing line, and we will say so plainly on the day one does.";

// ══ THE CLOSING SECTION ════════════════════════════════════════════════════════════════════════

// ══ THE LANDING FAQ ════════════════════════════════════════════════════════════════════════════
//
// ⚠️ MOVED HERE FROM `components/landing-faq.tsx` BY E9.46, and not for tidiness. Sitting inline in
// JSX it was seven paragraphs of claim-bearing prose that no denylist had ever read — and it had
// gone quietly FALSE: it answered "what sports does Credence cover?" with "MLB baseball only, for
// the 2026 season" and described the company as "a baseball analytics tool", on the very page now
// selling an NFL fantasy product. A marketing answer that contradicts the product is worse than a
// missing one, and it survived because nothing on either side of the repo was looking at it.

export const LANDING_FAQ: readonly { q: string; a: string }[] = [
  {
    q: "What does Credence actually do?",
    a: "Two things, under one method. For MLB we publish a daily card comparing our model's probability for each game against the price the market is offering, with the reasoning and the uncertainty attached. For the NFL we publish fantasy projections and rankings recomputed for your league's own scoring. Both are analysis tools. Neither is a picks service, and nothing is ever wagered or submitted on your behalf.",
  },
  {
    q: "Do you claim to do better than the betting market?",
    a: "No, and we would rather be direct about it than bury it. Our models have been tested against the closing line repeatedly and have not demonstrated a durable advantage over it — those results are recorded, including the ones we hoped would go the other way. What the MLB product offers is transparency: where our estimate differs from the market's, how sure we are, and how those calls have turned out. You decide what that is worth.",
  },
  {
    q: "What is Bayesian analytics, and why does it matter here?",
    a: "It treats a prediction as a distribution rather than a single figure. Instead of only saying \"62% home win\", the model also carries how confident it is in that estimate and revises it as new information lands. In practice it is why every number on this site arrives with a range beside it: the range is the part most models keep to themselves.",
  },
  {
    q: "What is the difference between the model number and the market number?",
    a: "The model number is the probability our model assigns to an outcome. The market number is the probability implied by the current odds once the sportsbook's margin is removed. The gap between them is disagreement — it tells you where our read and the market's read part company, which is not the same as telling you one of them is right.",
  },
  {
    q: "Is any of this automated betting?",
    a: "No. Automated placement is not possible in the US market, and we would not build it if it were. Every wager is your own manual decision.",
  },
  {
    q: "Which sportsbook are the MLB numbers priced against?",
    a: "Bovada, which is what our models are calibrated and compared against. If you use a different book the odds on your screen will differ, and the comparison shown here will not carry across directly.",
  },
  {
    q: "What is free, and what does a membership cover?",
    a: "The NFL rankings and projections are readable without an account, as is the full fantasy track record. A membership adds the daily MLB card and its research surfaces, and on the fantasy side the decision support — draft board, trade and waiver calls, and start/sit, all in your league's scoring.",
  },
]

export const HONESTY_STATEMENT =
  "Credence publishes the losses with the wins. The record on both products is computed over everything the model put its name to, not a selected subset, and the uncertainty around every estimate stays visible rather than being rounded away.";

export const FOOTER_CTA = {
  headline: "Start with the free half.",
  detail:
    "The NFL rankings and the full fantasy track record are open to anyone, no account required. A membership adds the daily MLB card and the draft, trade, waiver and start/sit calls in your league's own scoring.",
  disclaimer:
    "Everything here is analysis, published for information only. It is not financial advice, and you are solely responsible for any wager you choose to place.",
} as const
