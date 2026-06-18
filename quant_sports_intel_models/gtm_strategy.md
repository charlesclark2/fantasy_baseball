# Go-To-Market Strategy — Beyond Beta

**Status:** v0.1 — **draft for input** (a starting document for the GTM conversation, not a finalized plan).
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Date:** 2026-06-17
**North-star goal:** **100 paying monthly subscribers by NFL kickoff (~Sept 4, 2026).**
**Hard constraint (shapes everything):** we have **no demonstrated betting edge** and we don't claim one. GTM must sell **process, transparency, and depth** — never "we win." (Same honest-framing rule as the product; see `edge_program/edge_program_executive_summary.md`.)
**Companion docs:** `multi_sport_roadmap.md` (the NFL-kickoff timing), `edge_program_executive_summary.md` (the tiered value case), `baseball/fantasy/fantasy_dynasty_guide.md` (the Dynasty pillar).

> **🟢 BETA IS LIVE — first traction (2026-06-18):** onboarding shipped (E9.4/E9.5) + beta users provisioned; **5 active testers**, **≥3 daily users** validated via **PostHog**. This is the funnel's first real data point (baseline for the 100-subs north-star). Beta feedback already drives the E9 backlog — keep logging traction here as it grows.

## 0. Track separation & funding reality (decision, 2026-06-17)
- **Two separate tracks; the model backlog is primary.** The model is the platform's **quality core** — projections, CLV, props, and fantasy all *are* model outputs — so its backlog stands on its own merits and is prioritized independently. **GTM never reprioritizes model stories** (e.g. it does not pull betting-feature work to chase a launch date); the GTM-blocking pieces it *does* depend on (self-serve signup E9.7, Stripe E9.8) are tracked here, not by reordering the model backlog.
- **Funding reality — subscriptions, not betting profits, are the early revenue plan.** Betting is intentionally tiny *because* the edge is unproven (no demonstrated market edge; `best_alpha = 0`). Treat any betting P&L as **upside, not budgeted funding**, until it clears the gates (E1 PBO/DSR + a positive ≥100-game forward CLV). The model's near-term business value is **product quality** (what makes the subscription worth paying for) + **CLV as the leading indicator** of eventual edge. If the edge clears the gates, betting becomes a genuine second revenue stream — but the early days are funded by subscriptions, not by assuming betting profit.

## 1. The honest wedge (why anyone subscribes)
We are **not** another "lock of the day" tout. The defensible, honest positioning — *"the transparent, probabilistic sports tool"* — sells what we actually have:
- **Transparency / CLV education** — show users the *fair price*, the *breakeven line* (E9.1), and whether the market agreed with them (CLV). Teach line-shopping. This builds trust in a category full of scams.
- **Probabilistic depth** — full distributions, not a single number (E2); the "why" behind every pick (SHAP).
- **Dynasty / prospect projections (E8 / fantasy guide)** — the genuinely **underserved, defensible** product, with a real moat (minor-league→MLB translation) most competitors skip. *This is the GTM dark horse: it doesn't need a betting edge, it's year-round, and it's content-rich.*

> **Implication:** lead with **fantasy/Dynasty + transparency tools**, not "betting picks." It's more defensible, more ad-friendly, and isn't gated on beating the market.

## 2. North-star math (100 paid subs by kickoff)
At a typical freemium conversion of **3–5% free→paid**, 100 paid subs ⇒ **~2,000–3,300 free signups**. At ~25–40% visitor→free-signup on a good landing + free tool, that's **~6,000–13,000 relevant visitors** over the runway. Conclusion: the binding constraint is **top-of-funnel reach** (content + communities + free tools + referral), not the product — so the GTM build is a **content/community/referral engine**, fed by **free lead-magnet tools.** *(Numbers are planning placeholders — instrument and revise; §9.)*

## 3. ICP segments (3, prioritized)
1. **Dynasty / keeper fantasy players (lead segment).** Underserved, year-round, high willingness-to-pay for projections + prospect rankings, and reachable via content/communities. Our E8 prospect projections are the differentiator. *Also the bridge to NFL* (Dynasty football is huge).
2. **Process-minded sports bettors** who value CLV, fair-price transparency, and line-shopping (not tout-chasers). They convert on the honesty angle + the free +EV/CLV tools.
3. **NFL bettors + fantasy drafters (the kickoff spike).** Acquisition peaks late Aug–Sept (drafts + season hype). Time the paid push + NFL features to this moment.

## 4. Packaging & pricing (free → paid)
- **Free tier = lead magnets (top of funnel):** the parlay calculator (E10.1 — honest EV math), the +EV/breakeven price tool (E9.1), sample projections/rankings, and CLV/transparency views. These are shareable, SEO-able, and require no edge.
- **Paid tier = depth:** full distributional projections + Dynasty prospect board, player props, per-book CLV/edge, alerts.
- **Billing:** Stripe (edge guide E9.8), gated by Cognito groups; self-serve signup via E9.7 (Google OAuth). **These two stories are on the GTM critical path** — paid conversion can't happen without them.
- **Open decision:** price point + free-tier scope (§11).

## 5. Channels
- **Referral / word-of-mouth** (beta cohort) — instrument a referral incentive; beta users are the seed loop.
- **Content / SEO** (the engine) — CLV explainers, "is this +EV?" teaching, **Dynasty prospect rankings + rookie projections** (high-search, evergreen), transparency/methodology posts. Fits the honest brand and is ad-policy-safe.
- **Communities** — r/dynastyff, r/fantasybaseball, r/fantasyfootball, r/sportsbook, betting/fantasy X + Discords. Lead with the **free tools + rankings**, not picks.
- **Product-led growth** — free tools are the funnel; in-product nudges to paid.
- **(Defer) paid ads** — gambling ad restrictions are heavy; lean fantasy/projections + transparency for any paid acquisition, and only after organic conversion is proven.

## 6. Timeline to kickoff
- **Now → mid-July:** beta + free lead-magnet tools live; **Stripe + self-serve signup (E9.7/E9.8)**; referral loop; stand up the content engine (Dynasty rankings + CLV explainers). MLB is the summer proving ground + audience.
- **Mid-July → late Aug:** Dynasty fantasy push (offseason + MLB stretch-run content); **NFL pre-launch** — waitlist, rookie/Dynasty content, "NFL projections coming" capture; NFL data flowing (per `football/nfl/` + the lakehouse).
- **Late Aug → kickoff:** NFL **honest surfaces** live (projections, calculator, transparency — not edge claims); ride the **draft + kickoff acquisition spike** → the conversion moment for the 100-sub goal.

## 7. Why the calendar is the lever
MLB (now) = the **proving ground + summer audience + content**; **NFL kickoff = the acquisition spike** (fantasy drafts + betting peak); **Dynasty (year-round)** = the retention + differentiation engine that carries the offseason. The 100-sub target is realistic *only if* we use the kickoff spike — so the GTM build (tools, content, billing, NFL data) must be **ready before, not during, kickoff.**

## 8. KPIs
Free signups · **free→paid conversion %** · MRR · churn · **referral coefficient** · content traffic + top-converting pages · and the trust metric: **demonstrated CLV** (the honest proof that the product is worth paying for). Instrument from day one (PostHog/Vercel Analytics are already in the app, A0.4.19).

## 9. Risks & honest guardrails
- **No demonstrated edge** → never sell "winning." Sell process/transparency/projections. (Also the safest regulatory + trust posture.)
- **CAC / reach** is the real constraint → content + communities + free tools must do the heavy lifting; treat paid ads as a later, gated lever.
- **Churn** (results-chasing bettors) → retention leans on the **year-round Dynasty/projections** value, not weekly betting outcomes.
- **Ad/payment restrictions** for betting → fantasy/projections framing is more ad-friendly and processor-friendly.

## 10. Open decisions (need your input)
1. **Primary ICP / brand lead** — Dynasty-fantasy-first (recommended: defensible, year-round, ad-safe) vs betting-first vs balanced?
2. **Pricing** — monthly price point + annual option; free-tier scope (how much projection/CLV depth is free vs paid)?
3. **Referral incentive** — what do we give the beta cohort + new users for referrals?
4. **Paid-acquisition budget** — any, and when (pre- vs post- organic proof)?
5. **NFL-at-launch scope** — which honest surfaces must be live by kickoff to convert (projections + calculator + transparency, per the phased plan)?

*Next step once these are decided: turn this into a dated GTM execution plan with owners + the content calendar, and wire the conversion funnel (E9.7/E9.8 + analytics).*
