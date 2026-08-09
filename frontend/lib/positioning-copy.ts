// E9.60 — THE CANONICAL ABOUT + FAQ COPY. Every claim-bearing string those two pages render.
//
// ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
//
// NF-TR1 put the fantasy product's claims in `fantasy-claim-copy.ts`; E9.46 did the same for the
// home page in `home-copy.ts`. About and FAQ were the last two public marketing surfaces whose
// prose lived INLINE in JSX, unscreened by any denylist — and both had gone false:
//
//   · About led with "We forecast baseball the way the evidence supports" and a hero reading
//     "An honest maybe beats a confident guess", i.e. a page describing a one-sport company, on a
//     site whose home page now sells NFL fantasy first.
//   · FAQ answered "What sport(s) does Credence cover?" with "MLB baseball only, for the 2026
//     season" and called the company "a baseball analytics tool" — the exact sentence E9.46 had
//     already had to delete from the landing FAQ, still live one route over.
//
// `betting_ml/tests/test_e9_60_positioning_copy.py` parses THIS FILE'S string literals and runs the
// same `_CLAIM_DENYLIST` over them, exactly as the E9.46 and NF-TR1 suites do for their modules.
//
// ⛔ THE RULES THIS FILE IS WRITTEN TO, all inherited and none of them new:
//
//   1. NO PERFORMANCE CLAIM, IN EITHER VERTICAL. `best_alpha = 0`. No win rate, no ROI, no edge,
//      no "beats the market". The MLB program has six recorded no-edge results and the fantasy
//      track record's own 90% interval includes zero (NF-D17).
//   2. NO MEASURED NUMBER IS TYPED HERE. A figure typed into copy cannot be reconciled against the
//      measurement it came from. These pages link to the record; they never quote it.
//   3. ONLY WHAT IS LIVE READS AS LIVE. Weekly projections, start/sit, waivers and matchup tools
//      are NOT shipped; NFL and NCAAF betting intelligence are NOT shipped. Each is labelled.
//   4. ⛔ THE FREE BOARD IS SCRAPEABLE BY DESIGN and that was accepted when the tier was drawn
//      (`docs/freemium_tier.md` §1). Copy must never describe the paid line as protection against
//      scraping — it is about not printing the answer next to the question.
//
// ══ ⚠️ WHERE THIS DEPARTS FROM `docs/positioning_about_faq_nav_spec.md`, AND WHY ════════════════
//
// The spec calls the MLB track record PUBLIC in §3.3, §4.4 and §12 ("See the Track Record →").
// ⛔ IT IS NOT. Verified in `app/backend/main.py`: `picks.router` and `performance.router` are both
// mounted `dependencies=_paid`, so `/picks/scorecard`, `/picks/today`, `/picks/history` and
// `/performance` all refuse an anonymous caller. `home-copy.ts` already carries this correction and
// its guard forbids the phrase "public track record" outright.
//
// The spec's own §25 subordinates its wording to the live product ("Before publishing any factual
// mechanism statement, confirm it against the live product… If uncertain: VERIFY_LIVE_PRODUCT"), so
// following the live truth IS following the spec. The MLB record is therefore described as the
// members' scorecard throughout. ⭐ The FANTASY track record genuinely is public
// (`fantasy_public.router`, no gate) and is described that way — the asymmetry is real and is the
// reason both are named separately rather than as one "our record".

import { TRACK_RECORD_TRUST_LINK } from "@/lib/fantasy-claim-copy"

// ══ ABOUT — THE HERO ═══════════════════════════════════════════════════════════════════════════

/** ⭐ THE H1 IS THE SPEC'S, VERBATIM (§5). It is the one sentence that has to hold for a visitor
 *  arriving for either product, and it is a statement about METHOD rather than about outcomes —
 *  which is what makes it sayable at all under rule 1. */
export const ABOUT_HERO = {
  eyebrow: "Credence Sports",
  headline: "Better sports decisions start with knowing what you don't know.",
  subhead:
    "Credence Sports builds fantasy decision tools and betting intelligence around a simple idea: a projection is more useful when you can see the uncertainty around it, understand what is driving it, and judge it by what actually happened.",
} as const

// ══ ABOUT — WHY CREDENCE EXISTS ════════════════════════════════════════════════════════════════

export const ABOUT_WHY = {
  heading: "Why Credence exists",
  /** Rendered as separate paragraphs. The three examples are deliberately GENERIC illustrations of
   *  precise-looking numbers, not figures from our own product — see rule 2. */
  paragraphs: [
    "Sports analytics is full of precise-looking numbers. A player is projected for 17.4 fantasy points. A team has a 61% chance to win. A market supposedly has a 4% gap to close.",
    "The number is rarely the whole answer. How uncertain is it? What assumptions produced it? How often has the model been right before? Does the apparent difference survive proper testing? What should you actually do differently because of it?",
    "Credence Sports exists to make those questions part of the product rather than something hidden behind the model.",
  ],
  pullQuote:
    "We are not trying to eliminate uncertainty from sports. We are trying to measure it well enough to make better decisions inside it.",
} as const

// ══ ABOUT — TWO PRODUCTS, ONE STANDARD ═════════════════════════════════════════════════════════
//
// ⭐ FANTASY FIRST, everywhere on this page and in the nav (spec §2). Fantasy is the current
// acquisition priority and the home page already leads with the fantasy proof; a visitor should
// never have to infer different product priorities from different pages.
//
// ⚠️ THE `live` / `coming` SPLIT IS THE POINT OF THE SHAPE. It is data rather than prose so the
// guard can assert that no un-shipped capability sits in a `live` list, and so the page can render
// the two groups differently. A weekly tool moved into `live` before it ships is then a red build,
// not a sentence someone has to notice.

export type ProductBlock = {
  key: "fantasy" | "betting"
  label: string
  lede: string
  live: { heading: string; items: readonly string[]; note: string }
  coming: { heading: string; items: readonly string[]; note: string }
}

export const ABOUT_PRODUCTS: readonly ProductBlock[] = [
  {
    key: "fantasy",
    label: "Fantasy decision tools",
    lede: "Credence turns player projections into rankings and decisions that reflect the league you actually play in rather than a generic scoring format.",
    live: {
      heading: "Available now",
      // ⚠️⚠️ VERIFY_LIVE_PRODUCT — AND THIS LIST IS SHORTER THAN THE SPEC'S ON PURPOSE.
      //
      // Spec §3.1/§7 lists "Per-league personalization" as Available now. ⛔ IT IS NOT SAFE TO SAY
      // SO HERE. The free one-personalized-league grant (G100-C1's `FREE_PERSONALIZED_LEAGUE_QUOTA`)
      // is IN FLIGHT: the code is on `main`, but the API Lambda ships only via a manual
      // `deploy.sh`, so a merged quota is not a served one — and the operator flagged it as not yet
      // shipped. There is no anonymous probe that can settle it either, because every saved-league
      // route needs an account and the gateway's Cognito authorizer answers 401 before the Lambda
      // runs (NF3.2), so a 401 cannot distinguish "deployed and gated" from "not deployed".
      //
      // ⭐ WHAT IS VERIFIED, and how: the three below were read from the LIVE production board on
      // 2026-08-09 — `GET /api/public/board?config=full_ppr&size=12` anonymously returned 858 rows,
      // ZERO of them `locked`, every one carrying `pts` and a `ptsP10`/`ptsP90` band. That is the
      // whole claim: rankings, projections and ranges, free, with nothing withheld.
      //
      // Personalization is therefore described where it is unambiguously true in BOTH states — as
      // what a membership adds (`docs/freemium_tier.md`: the free tier is a QUOTA granted against a
      // PAID capability, never a reclassification of it). When the free grant is confirmed live,
      // this list gains it back in the same change that updates the FAQ.
      items: ["Draft rankings", "Player projections", "Projection ranges"],
      note: "Free to read without an account: every player we project, our rank for him, the 80% range on his season, and the market's ADP beside it. A membership re-scores that board for your own league's scoring and roster.",
    },
    coming: {
      heading: "Coming this season",
      items: [
        "Weekly projections",
        "Start/sit decision support",
        "Waiver tools",
        "Matchup-aware recommendations",
      ],
      // ⛔ Required. Without it the two lists read as one feature set with a formatting variation.
      note: "These are not built yet. Nothing on the site treats them as available, and this list is where they are tracked until they are.",
    },
  },
  {
    key: "betting",
    label: "Betting intelligence",
    lede: "Credence compares model-implied probabilities with the betting market, shows where they disagree, and keeps the uncertainty around the estimate attached to it. A model-market gap is information. It is not automatically a bet.",
    live: {
      heading: "Available now",
      items: ["MLB betting intelligence"],
      note: "Model probabilities, the de-vigged market consensus beside them, the distance between the two, and the range around our estimate — graded against the market afterwards, losses included.",
    },
    coming: {
      heading: "Coming this season",
      items: ["NFL betting intelligence", "NCAAF betting intelligence"],
      // ⭐ Deliberately the same shape as the home page's `ROADMAP_NOTE`: both un-shipped rows are
      // the SAME product as the MLB one, not a different and better one that wins.
      note: "Both are the same product as the MLB one — model projections, the market's number beside them, and the record kept in the open. Neither has shipped.",
    },
  },
]

// ══ ABOUT — WHAT WE BELIEVE ════════════════════════════════════════════════════════════════════

/** ⭐ Five principles (spec §8), against the home page's four. The fifth — separating disagreement
 *  from edge — has no home-page equivalent and is the one this site most needs stated outright,
 *  because it is the exact inference a visitor draws unprompted from a model-vs-market card. */
export const ABOUT_BELIEFS: readonly { index: string; title: string; detail: string }[] = [
  {
    index: "01",
    title: "Show the uncertainty.",
    detail:
      "Every estimate carries a range, a distribution, or another measure of how sure we are, wherever the model supports one. A wide interval is information, not a flaw — it tells you how much confidence the evidence actually warrants.",
  },
  {
    index: "02",
    title: "Grade the whole record.",
    detail:
      "We publish wins and losses rather than the observations that happened to go well. Our MLB picks are scored against the market after the game on the members' scorecard, and every past fantasy season is scored against what happened, one row per player, in a track record open to anyone.",
  },
  {
    index: "03",
    title: "Show the work.",
    detail:
      "A projection is more useful when you can see what moved it. Where the model supports it we expose the inputs, the drivers, the market comparison, the uncertainty and the evaluation history — so you can disagree with us and see exactly where.",
  },
  {
    index: "04",
    title: "Retire what fails.",
    detail:
      "Models and hypotheses have to clear evaluation gates set before the answer is known. When an idea does not survive proper testing we close it out, in the changelog, with the reason — rather than changing the test until it passes. Several have been.",
  },
  {
    index: "05",
    title: "Separate disagreement from edge.",
    detail:
      "A model disagreeing with a market or a consensus does not establish that the model is right. Model-market disagreement, evidence of signal, and something you can act on are three different things, and we do not treat them as interchangeable.",
  },
]

// ══ ABOUT — THE PULL QUOTE ═════════════════════════════════════════════════════════════════════

/** ⭐ RETAINED FROM THE PRE-E9.60 PAGE, DEMOTED FROM H1 (spec §9). It was the About hero when
 *  Credence was one product; it is a good line and a bad thesis statement, because it describes our
 *  posture rather than what we build. Kept inside the page so the rewrite is not a deletion. */
export const ABOUT_PULL_QUOTE = {
  quote: "An honest maybe beats a confident guess.",
  support:
    "Especially when the maybe arrives with a probability, a range, and a record you can inspect.",
} as const

// ══ ABOUT — RANGES, EVALUATION, ACCOUNTABILITY ═════════════════════════════════════════════════

/** ⛔ `appearsIn` NAMES ONLY SHIPPED SURFACES (spec §10). Weekly lineup win probabilities, weekly
 *  matchup simulations and in-season outcome simulations are NOT live and must not appear here —
 *  this is the section where advertising roadmap work as a capability would be most tempting and
 *  least visible. */
export const ABOUT_RANGES = {
  heading: "We model ranges, not just answers.",
  body: "Sports outcomes are noisy, so a projection should carry more than a single point estimate. Credence uses predictive distributions, probability estimates and calibrated ranges wherever the model supports them, so you can see not only what the model expects but how much confidence the evidence warrants.",
  appearsInHeading: "Today that shows up in",
  appearsIn: [
    "Fantasy player projection ranges",
    "MLB model probabilities and their uncertainty",
    "Model-versus-market comparisons",
  ],
} as const

/** ⛔ NOTHING ABOUT SYNTHETIC VALIDATION / SIM-V1 GOES HERE until that capability is operational
 *  (spec §11) — the same rule `home-copy.ts` carries on the methodology section. Advertising
 *  roadmap work as shipped, on the one section whose subject is our standard of evidence, would be
 *  self-refuting. */
export const ABOUT_EVALUATION = {
  heading: "The model does not get to grade its own homework.",
  paragraphs: [
    "Every serious model change is tested against explicit benchmarks and held-out data. New features have to beat simpler alternatives. More complex models have to justify their complexity. Calibration matters, and so does whether a result survives reasonable validation.",
    "When a result is underpowered, we call it underpowered. When a signal disappears under proper testing, we say so. When the market remains the better estimate, we say that too.",
  ],
  pullQuote:
    "Our goal is not to make every research question produce a winning model. It is to make the answer trustworthy.",
} as const

/** ⭐⭐ THE HONEST LIMIT, AND THE SECTION MOST AT RISK OF BEING SOFTENED LATER.
 *
 *  Both halves are load-bearing and they pull against each other: copy implying we do not measure
 *  ourselves would be as false as copy claiming an edge, because the daily model-vs-market record is
 *  computed every day with losses included. What that record has not shown is a durable advantage
 *  over the closing market. Dropping the first half throws away the most credible thing the product
 *  has; dropping the second is the overclaim `best_alpha = 0` forbids.
 *
 *  ⚠️ THE TWO RECORDS ARE NAMED SEPARATELY BECAUSE THEIR ACCESS DIFFERS — see the module header. */
export const ABOUT_ACCOUNTABILITY = {
  heading: "Wins and losses both belong on the page.",
  paragraphs: [
    "Credence keeps a record of the forecasts and model-market comparisons it publishes. Every MLB pick is scored against the market consensus after the game and lands on the members' scorecard; every past fantasy season is scored against what actually happened, in a track record open to anyone with no account required.",
    "The point is not to turn every correct call into a victory lap. It is to keep the whole record inspectable, including the forecasts that were wrong and the stretches where the market was the better estimate.",
    "What that record has not shown is a durable advantage over the closing market, and we would rather say so here than let the page imply otherwise. Transparency only means anything if the losing observations stay on it too.",
  ],
} as const

// ══ ABOUT — WHO IT IS FOR, AND WHAT THIS IS NOT ════════════════════════════════════════════════

export const ABOUT_AUDIENCE = {
  heading: "Credence is for the person who wants to know why.",
  paragraphs: [
    "The fantasy player who wants to know why a player is ranked differently in their league. The bettor who wants to see the model probability sitting beside the market consensus. The fan who already knows that a projection without uncertainty is incomplete.",
    "And the person who would rather be told the evidence is weak than be sold confidence the model has not earned.",
    "If you have ever opened a player page because a ranking looked wrong, and wanted to understand the mechanism rather than simply accept the number, this was built for you.",
  ],
} as const

/** ⭐ THE NEGATIVE SPACE, and the cheapest honest positioning on the site. Each line forecloses a
 *  specific misreading a visitor arrives with.
 *
 *  ⚠️ WORDING IS CONSTRAINED BY THE DENYLIST and this is worth recording before someone "improves"
 *  it back: the spec's own §4.3 phrasing is "not a guaranteed recommendation", and "guaranteed" is a
 *  DENIED substring. A screening pass cannot see the "not" in front of it — the same reason
 *  `home-copy.ts`'s roadmap note had to be rewritten rather than negated. A rewrite must AVOID the
 *  denied phrasing, never disclaim it. */
export const ABOUT_NOT = {
  heading: "What Credence is not",
  items: [
    "Not a tout account, and not a service that sells you winners.",
    "We do not place, size or submit bets on your behalf. Every wager is your own decision and your own action.",
    "We do not treat every model-market difference as something you can act on.",
    "We do not label the featured MLB read as the day's best bet or its biggest opportunity.",
    "And we do not hide uncertainty because a cleaner number is easier to market.",
  ],
  closer: "Credence provides decision intelligence. The decision remains yours.",
} as const

// ══ ABOUT — THE CLOSING CTA ════════════════════════════════════════════════════════════════════

/** ⛔ EVERY HREF HERE IS A ROUTE THAT EXISTS AND SERVES THE CALLER IT IS OFFERED TO. The fantasy
 *  rankings and the fantasy track record are genuinely open to an anonymous visitor; `#today` is the
 *  home page's own public MLB read (the same target `VERTICALS[betting].cta.href` uses). ⛔ Do not
 *  add `/performance` here — it is behind the paid guard, and a closing CTA that drops a stranger
 *  into a login wall is the one surprise this page cannot afford (E9.56c's dead `/pricing` class). */
export const ABOUT_CTA = {
  heading: "Questions about how Credence works?",
  detail:
    "The FAQ covers how the market consensus is calculated, what the ranges mean, how MLB projections update through the day, how fantasy rankings are personalized, and how a model earns its way into the product.",
  buttons: [
    { label: "Read the FAQ", href: "/faq", primary: true },
    { label: "See the free rankings", href: "/fantasy/rankings", primary: false },
    { label: TRACK_RECORD_TRUST_LINK.label, href: TRACK_RECORD_TRUST_LINK.href, primary: false },
    { label: "Today's MLB read", href: "/#today", primary: false },
  ],
  footnote: "A product of Penumbra Partners.",
} as const

// ══ THE FAQ ════════════════════════════════════════════════════════════════════════════════════
//
// ⭐ SECTION ORDER IS THE SITE'S PRODUCT ORDER (spec §17): About → Fantasy → Betting → Trust.
//
// ⚠️ `link` EXISTS SO PROSE STAYS SCREENABLE. An answer that needs an anchor (the support mailto,
// the track record) would otherwise have to be JSX, which is exactly how the pre-E9.60 FAQ ended up
// with one answer no denylist could read. The prose stays a plain string; the anchor is data.
//
// ⛔ WHAT WAS DELETED FROM THE OLD FAQ AND MUST NOT COME BACK, each for its own reason:
//
//   · "What is Kelly % and how much should I bet?" — stake sizing presumes something to size
//     against. Spec §18.9: with no demonstrated edge, the public FAQ carries no bet-sizing
//     guidance. ⚠️ THE FEATURE IS STILL LIVE behind the paywall (`/ev-tracker` renders raw and
//     capped Kelly columns; `/settings` has a Kelly cap) — removing it is a PRODUCT decision
//     outside E9.60's scope and is flagged for the operator, not silently done here.
//   · "MLB baseball only, for the 2026 season" — false since the fantasy product shipped.
//   · "Bovada is the benchmark we use for edge detection" — conflated two different things. The
//     comparison probability is a de-vigged consensus across every book pricing both sides; Bovada
//     is where a pick's PRICE is shown and graded. Both facts are kept, separated.
//   · The "picks service" framing throughout.

export type FaqItem = {
  q: string
  a: string
  link?: { label: string; href: string }
}

export const FAQ_SECTIONS: readonly { category: string; items: readonly FaqItem[] }[] = [
  {
    category: "About Credence",
    items: [
      {
        q: "What does Credence Sports actually do?",
        a: "Two products, one standard of evidence. For fantasy football we publish draft rankings, player projections, the 80% range around each one, and personalization for the league you actually play in. For MLB betting intelligence we publish model probabilities, compare them against the betting market, show the uncertainty around the estimate, and grade every published read afterwards. Credence is an analytics and decision-support platform: it does not place bets on your behalf, and it is not a picks service.",
      },
      {
        q: "What does probabilistic sports analytics mean?",
        a: "It means the model estimates a distribution rather than a single number. Instead of only saying \"62% home win\" or \"17.4 points\", it also carries how much of that estimate is genuine uncertainty — and updates as evidence arrives. In practice that is why a fantasy projection ships with an 80% band, why a game probability carries a credible interval, and why some of our estimates tighten as a season accumulates data.",
      },
      {
        q: "Why does Credence show uncertainty when other sites show one number?",
        a: "Because a single number hides the thing you most need in order to act on it. Two players can carry the same projection with completely different spreads around it, and that difference is often the whole decision. A wide interval is not an embarrassment — it tells you which calls are close enough that reasonable people should disagree, and which are not.",
      },
      {
        q: "What sports does Credence cover?",
        a: "NFL fantasy football and MLB betting intelligence are live today. NFL and NCAAF betting intelligence are coming this season and have not shipped. On the fantasy side, draft rankings, player projections and projection ranges are available now, with personalization for your own league's scoring and roster part of a membership; weekly projections, start/sit, waiver tools and matchup-aware recommendations are also still to come.",
      },
    ],
  },
  {
    category: "Fantasy football",
    items: [
      {
        q: "How are Credence rankings different from consensus rankings?",
        a: "A consensus ranking is an average of what other rankers think. Ours is built from a projection model and then scored under a specific set of league rules, so the ordering follows from the projections and the scoring rather than from agreement. That means we will sometimes sit a long way from the crowd on a player — which is a difference to look into, not on its own a reason to think we are right.",
      },
      {
        q: "Are rankings customized for my league?",
        a: "Yes, with a membership. Save your league's real scoring, roster shape and team count and the whole board re-scores against it — including value over replacement, which depends entirely on how many of each position your league actually starts. The board everyone can read without an account is full-PPR at twelve teams, and every number on it is real.",
        link: { label: "See what a membership adds", href: "/subscribe" },
      },
      {
        q: "What scoring formats are supported?",
        a: "Full-PPR at twelve teams is free for everyone, with no account. The other scoring formats and league sizes — half-PPR, standard, superflex, three-receiver, and ten- or twelve-team — are re-scored for members. League size is not cosmetic: it moves the replacement level, so it moves the ranking.",
      },
      {
        q: "Why are Credence's projected points lower than other sites'?",
        a: "Because our headline number is availability-weighted. The chance a player misses games is already multiplied through it, so it answers the question \"how many points should we expect across the season, accounting for both performance and the chance he is unavailable?\" Many sites publish something closer to \"what this player would score if he played every week\", which will naturally read higher. We show a full-season rate beside the total for exactly that comparison, and projected games sits next to both.",
      },
      {
        q: "Why can a player's Credence rank differ from where he is being drafted?",
        a: "ADP is where a player is actually going in drafts; our rank is where our projection puts him under a set of scoring rules. The two answer different questions, so a gap between them is a disagreement worth inspecting rather than a mistake on either side. The player page shows what is driving our number so you can see where the difference comes from and decide for yourself.",
      },
      {
        q: "What does the projected range mean?",
        a: "It is an 80% interval: our model's estimate of the band the player's season total is most likely to land inside. Roughly one season in five should finish outside it, and that is the design rather than a failure. A wide band means the evidence genuinely supports a wide set of outcomes — which is a real thing to know about a player before you spend a pick on him.",
      },
      {
        q: "What is free, and what does a membership cover?",
        // ⚠️ SCOPED TO WHAT IS VERIFIED SERVING — see the note on `ABOUT_PRODUCTS`. The free
        // one-personalized-league grant is in flight, so it is not promised here; the sentence is
        // true whether or not that grant is live yet.
        a: "Free, including without an account: the full rankings board at full-PPR twelve teams, the format-independent projections, the 80% ranges, market ADP beside our number, every player page and player search. Nothing on those pages is withheld or blurred. A membership adds the other scoring formats and league sizes, personalization for your own league's scoring and roster, and the decision tools — the draft optimizer, and the weekly calls as they land.",
        link: { label: "See what a membership adds", href: "/subscribe" },
      },
      {
        q: "Can I use Credence for more than one league?",
        a: "Personalized leagues are part of a membership, which also carries the cross-league view where every saved roster is scored under its own format in one place. A league can be imported from a supported platform, or typed in by hand if we cannot reach yours.",
      },
    ],
  },
  {
    category: "Betting intelligence",
    items: [
      {
        q: "What is the difference between Model % and Market %?",
        a: "Model % is the probability our model assigns to an outcome from the game's own inputs — pitching, offense, bullpen, park and run environment. Market % is what the consensus price implies once the sportsbook's margin is stripped out. The distance between them is disagreement, and that is all it is: it locates where our read and the market's part company, which is not the same as establishing which of them is right.",
      },
      {
        q: "What market are the MLB probabilities compared against?",
        a: "A de-vigged market consensus, not one designated sportsbook. For each game we take every book pricing both sides before first pitch, convert its two-way prices into implied probabilities, and normalise them to sum to one — that removes the book's built-in margin, which is what makes the number comparable to a model probability at all. The consensus is then a plain average across those books, with none weighted above another. Individual books can sit away from it, so the price available to you may not match the consensus exactly.",
      },
      {
        q: "What does \"our models agree\" mean?",
        a: "It means two independent Credence models landed within two points of each other on that game — one estimating the win probability directly, the other from the projected run differential. It is computed without looking at the odds at all. It is a statement about our own models agreeing with each other: it is not a confidence rating for a wager, not proof of a mispricing, and not a forecast that the outcome will happen.",
      },
      {
        q: "Does model-market disagreement mean there is an edge?",
        a: "No. A disagreement tells you our estimate differs from the market's consensus estimate. That is useful information and a reasonable place to look closer, but it does not establish that we are right. Our own record has not shown a durable advantage over the closing market, and we publish that result rather than working around it.",
      },
      {
        q: "What is the featured MLB read on the home page?",
        a: "It is one game where our model and the market disagree, shown as a worked example of what the product does. We take the games where our two independent models land close to each other, then feature the one whose number sits furthest from the market's. Featuring the largest gap on the board also means featuring the read most likely to be ours getting something wrong rather than the market's, which is why the card says so. It is a demonstration, not a recommendation, and it is not labelled the day's best bet.",
      },
      {
        q: "What does Expected Value mean on the EV tracker?",
        a: "Expected Value is the arithmetic value a price would carry if the probability estimate behind it were correct. That conditional is the whole point: a positive number is a statement about our model's estimate, not evidence that the estimate is right or that the result is repeatable. It should be read alongside the uncertainty on the estimate and the record, which has not demonstrated a durable advantage over the closing market.",
      },
      {
        q: "What does \"Preliminary\" mean?",
        a: "Preliminary projections are produced before confirmed lineups are available, so they rely on probable starters and available roster information. Once official lineups post, the model is re-run with the confirmed players and the estimate can change. \"Preliminary\" describes the information the projection had, not how confident it is.",
      },
      {
        q: "What does projected vs. confirmed lineup mean?",
        a: "Confirmed means the official lineup has been submitted and is locked. Projected means we are using our best estimate of who starts, from probable-pitcher feeds and historical patterns, and it can still change. A read computed on a confirmed lineup has the actual player inputs; a projected one does not yet.",
      },
      {
        q: "How often are predictions updated?",
        a: "The model runs each morning and publishes after roughly 9am ET on probable starters and available data. Reads are then re-scored through the day as lineups are confirmed and odds move, so the version closest to first pitch is the one computed on the most information. Some days no game qualifies for the featured read at all, which is a real answer rather than a gap in the page.",
      },
      {
        q: "Is this automated betting?",
        a: "No. Automated placement is not possible in the US market, and we would not build it if it were. Credence publishes analysis; every wager is your own manual decision, on your own account. Nothing is ever placed, sized or submitted for you.",
      },
      {
        q: "Is sports betting legal?",
        a: "It depends entirely on where you are. Some jurisdictions allow online betting through licensed operators and others do not. Credence Sports provides analytics only — we are not a licensed gambling operator and nothing here is legal advice. Understanding and complying with the rules where you live is your responsibility.",
      },
      {
        q: "What happens when a game is postponed?",
        a: "Postponed games are voided in your bet log: the stake comes back and the game does not count toward your record. If the game is rescheduled and you want to track a wager on it, log that separately.",
      },
    ],
  },
  {
    category: "Trust and methodology",
    items: [
      {
        q: "Does Credence claim to beat the betting market?",
        a: "No — and the distinction matters more than the answer. We do measure it: every MLB read is scored against the market after the game, wins and losses alike, and that daily record is part of the product rather than something we keep quiet about. What the record has not shown is a durable advantage over the closing market. Publishing where our model disagrees with the market, and how those disagreements turned out, is a different and far more defensible thing than claiming those disagreements can be reliably converted into returns.",
      },
      {
        q: "Where can I see the record?",
        a: "The fantasy track record is open to anyone with no account: every past season scored against what actually happened, one row per player, over the whole set rather than a chosen subset. The MLB model-vs-market record is graded daily and lives on the members' scorecard, so it needs an account to read.",
        link: { label: TRACK_RECORD_TRUST_LINK.label, href: TRACK_RECORD_TRUST_LINK.href },
      },
      {
        q: "Does Credence publish losing results?",
        a: "Yes, and it is the part of this that is worth checking. Research that fails its own pre-registered gates is closed out in the changelog with the reason it failed, including cases where a promising idea did not survive validation. The records are scored over the whole set, not over a window chosen after the fact.",
        link: { label: "See what we shipped and closed", href: "/changelog" },
      },
      {
        q: "How are the models built?",
        a: "We use different model families for different prediction problems rather than forcing every product through one algorithm. The live models include statistical and machine-learning approaches selected by out-of-sample evaluation, calibration testing and comparison against simpler alternatives — a new feature has to beat the simpler version of itself before it ships. Inputs differ by product: the MLB game models read pitching matchups, team offense and defense, park factors, umpire tendencies and weather, among others.",
      },
      {
        q: "How does Credence evaluate a new model?",
        a: "Against benchmarks and held-out data, on criteria written down before the answer is known. A candidate is compared against simpler alternatives and against deliberately naive baselines that it has to beat; complexity has to justify itself; and calibration is judged alongside accuracy, because a model that is right on average and wrong about its own confidence is not much use for a decision.",
      },
      {
        q: "What happens when a model fails its evaluation?",
        a: "It does not ship, and the result is recorded. Sometimes the honest finding is that an effect is real but the data cannot yet resolve it, which is a different answer from the effect not being there — we distinguish those rather than rounding both to \"no\". When a shipped model stops clearing its gates, it is retired rather than quietly left in place.",
      },
      {
        q: "How do I report a data issue?",
        a: "If you see incorrect odds, a wrong score, a missing game, or a projection that looks wrong, tell us and we will investigate. Include the player or game and the date.",
        link: { label: "support@credencesports.com", href: "mailto:support@credencesports.com" },
      },
    ],
  },
]

export const FAQ_HEADER = {
  eyebrow: "Credence Sports · A product of Penumbra Partners",
  heading: "Frequently asked questions",
  /** ⭐ The About/FAQ/Track-record division the spec draws in §16, said to the reader rather than
   *  left as an internal content rule: About is why, FAQ is how, the record is what happened. */
  subhead:
    "How Credence works — the mechanisms, the definitions, and the limits. For why any of it exists, read About; for what actually happened, read the record.",
} as const

// ══ NAVIGATION ═════════════════════════════════════════════════════════════════════════════════
//
// ⭐⭐ THE DEFECT THIS FIXES, and it is the largest of the three in E9.60: a signed-out visitor had
// NO DOOR TO THE BETTING PRODUCT ANYWHERE IN THE NAV. `publicNavItems()` flattens every
// `public: true` item in `nav-model.ts`, and all four of them (Rankings, Projections, Player Search,
// fantasy Track Record) are FANTASY. So the nav of a company whose home page sells two products
// listed exactly one of them — while the MLB half is the older, live, revenue product.
//
// ⚠️ WHY `/#today` AND NOT A BETTING PAGE. There is no public MLB route to send them to: `/dashboard`,
// `/performance`, `/picks/*`, `/props` and `/ev-tracker` are all mounted `dependencies=_paid`. The
// ONE public MLB surface in the product is the home page's featured read, which renders from
// `/api/public/featured` through the G100-D1 CDN route — so `/#today` is the honest door, and it is
// the same target the home page's own betting CTA uses (`VERTICALS[betting].cta.href`). ⛔ Do not
// "improve" this to `/performance`: that is a login wall wearing a product label.
//
// ⚠️ ORDER IS FANTASY-FIRST (spec §2/§20), matching the home page's `VERTICALS`.

export type SignedOutNavLink = {
  label: string
  href: string
  /** ⭐ The DESKTOP label, when the full one is too long for a single bar.
   *
   *  ⚠️ THIS EXISTS BECAUSE OF A REAL CONSTRAINT, not for tidiness. E9.58 already recorded this bar
   *  overflowing on a phone — the wordmark overlapped the first link and "Track Record" wrapped
   *  onto two lines — and E9.60 both ADDS a link (the MLB door) and BUMPS the type size (the E9.61
   *  nav-sizing note, absorbed here). "MLB betting intelligence" at `text-sm` beside three other
   *  links and two buttons does not fit a laptop bar. The mobile menu, which has the room and the
   *  product grouping, keeps the full descriptive label. */
  short?: string
  /** Which product this door belongs to; `null` for the company-level pages. Rendered as a group
   *  separator on mobile, where there is room to group. */
  product: "fantasy" | "betting" | null
  /** Desktop shows a trimmed set — the bar overflows on a laptop at more than about five links.
   *  Mobile shows everything (spec §22), which is where FAQ becomes reachable from the nav at all. */
  desktop: boolean
}

/** ⛔ EVERY ENTRY MUST BE REACHABLE BY THE VISITOR IT IS DRAWN FOR. This list renders ONLY when
 *  signed out, so each href has to serve an anonymous caller — a nav item whose only behaviour is a
 *  redirect to /login is a menu that lies about what it opens (`nav-model.ts`'s `freeSignedIn`
 *  doc records the same rule for the signed-in menu). */
export const SIGNED_OUT_NAV: readonly SignedOutNavLink[] = [
  { label: "Fantasy rankings", short: "Fantasy", href: "/fantasy/rankings", product: "fantasy", desktop: true },
  { label: "Projections", href: "/fantasy/projections", product: "fantasy", desktop: false },
  { label: "Player search", href: "/fantasy/players", product: "fantasy", desktop: false },
  // ⭐ TRACK RECORD IS TOP-LEVEL (spec §20/§21, operator 2026-08-09) — it is the site's central
  // trust asset and the one record a stranger can read without an account, so it earns a bar slot
  // rather than living only inside a product menu.
  {
    label: "Fantasy track record",
    short: "Track Record",
    href: TRACK_RECORD_TRUST_LINK.href,
    product: "fantasy",
    desktop: true,
  },
  // ⭐ THE DOOR THAT WAS MISSING.
  { label: "MLB betting intelligence", short: "MLB", href: "/#today", product: "betting", desktop: true },
  { label: "About", href: "/about", product: null, desktop: true },
  { label: "FAQ", href: "/faq", product: null, desktop: false },
]

// ══ THE FOOTER — DELIBERATELY NOT DECLARED HERE ════════════════════════════════════════════════
//
// E9.60 adds About and Track Record to `components/site-footer.tsx`, but leaves the link set as a
// LITERAL ARRAY in that component rather than lifting it into this module, which is the opposite of
// what the rest of this file does and is worth the note:
//
//   · `test_e9_46_home_copy.py::test_the_blog_is_still_reachable` asserts the string `href: "/blog"`
//     appears in the footer SOURCE. It is the half that makes the blog's demotion from the nav a
//     demotion rather than a deletion, and a data-driven list would make it vacuously false.
//   · `test_e9_56c_cta_routes.py` scans `.tsx` files for literal `href="/…"` to catch a link
//     pointing at a route with no `page.tsx`. A `.ts` data module is outside that scan.
//
// Footer links are chrome, not claims, so they gain nothing from screening here and would lose two
// guards by moving. ⛔ Do not "tidy" them into this file without relocating both.
//
// ⚠️ The same trade-off does NOT apply to `SIGNED_OUT_NAV` above: those entries carry PRODUCT
// POSITIONING (which products exist, in what order), which is exactly what this module governs — so
// its route coverage is re-closed explicitly by `test_e9_60_positioning_copy.py` instead.
