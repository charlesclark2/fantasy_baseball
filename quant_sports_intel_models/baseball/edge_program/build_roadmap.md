# Baseball Build Roadmap — Two Tracks (now → MLB All-Star break)

**Status:** living · **Window:** now → the **MLB All-Star break (~mid-July 2026)** · **Scope: baseball only.**
**Last synced:** 2026-06-18 — **🚨 E2.1b OVERTURNED THE E1 HEADLINE:** the program's #1/#2 feature (`bp_eb_xwoba`) is a **within-game leak** → "bullpen dominates / invest in bullpen" is RETRACTED; real signal is modest (coverage/uncertainty); **new top model-track items = E1.7 de-leak** (names the offline→live collapse mechanism) **+ E1.8 full leakage sweep** (if the #1 feature leaked, others may — may explain the broad H2H+Totals collapse). **E1 COMPLETE** (gate set) but finding #3 retracted; **E4 closed** (CLV-too-small) but **H2H model stays live through beta**; E3.0/E3.0b ✅; **E2.1 ✅ gate-pass** (swap bullpen channel to leakage-safe before serving); slim re-promote **gated on E6.7 + re-derive post-de-leak**; E3.3 parked. App track: **E9.13 + E9.15 + E9.10 ✅ SHIPPED 2026-06-18 → E9.5 current** (E9.10 added the live `/users/profile` endpoint → unblocks E9.17; changelog page now shows the full Mon–Sun range); Track 2 **reconciled** with the guide's E9 backlog (added E9.3/E9.9/E9.10; parked E9.7/E9.8/E10.1 flagged). **🟢 SES PRODUCTION GRANTED 2026-06-18** (50k/day, out of sandbox) → unblocks E9.4/E9.5 + E9.9's email path; Resend Path B retired; E9.5/E9.4 bumped up as beta-launch enablers. **Changelog convention noted: weeks group Monday→Monday** (§0.2); new **E9.18** (changelog accordion) added.
**Purpose:** the persisted, ordered execution backlog (the Trello source-of-truth) for the two parallel tracks. Distinct from the edge guide **§7** (dependency/lane logic) and `../../multi_sport_roadmap.md` (the cross-sport, fall-targeting strategy). Full story specs live in `edge_program_implementation_guide.md`; standalone prompts in `story_prompts.md`.

**Scope rule for this window:** **strictly baseball.** Multi-sport (NFL/NCAAF/NCAAB) and the Fantasy/Dynasty vertical are **parked** until after the break (see *Out of scope* below). The two tracks below are independent and run in parallel; the **model track is primary** (the platform's quality core), the **app track** ships beta-facing value on top.

---

## Track 1 — Model build  *(2 model sessions: A = validation/totals · B = market)*
Ordered; lane in brackets. **E1's go-live gate is now CLEARED (E1.1–E1.6 ✅ + PBO/DSR + purged-CV on record)** — E2–E5 can promote to live once each clears its gate (PBO<0.2 + DSR>0 + forward-CLV).

| # | Story | Title | Lane | Note |
|---|-------|-------|------|------|
| — | **E2.1** ✅ | Per-side count-distribution model | A·market-blind | ✅ **GATE PASS 2026-06-18** — NegBin beats Poisson (5/5 folds, +0.093 NLL), overdispersion recovered. ⚠️ **Before serving, swap its bullpen channel to the leakage-safe aggregate** (E2.1b found the incumbent `bp_eb_xwoba` is a within-game leak — not computable live). Artifact `totals_perside_v1.pkl` (not promoted). |
| — | **E2.1b** ✅ | Bullpen model deepening (`bullpen_v3`) | A·market-blind | ✅ **COMPLETE 2026-06-18 — gate FAIL by design = the finding.** Deepening can't beat the incumbent because the incumbent (`bp_eb_xwoba`) is a **within-game leak** (weights each reliever's EB by `outs_in_game`). Proven 3 ways (leak-signature NLL, source, MDA collapse #1/#2→noise). **Deliverable = the leak discovery + a leakage-safe replacement + the de-leak card (E1.7).** `bullpen_v3` NOT promoted (no lift). See `E2_1b_HANDOFF.md`. |
| 1 | **E1.7** ⭐ | **De-leak the production bullpen feature** (Tier-0 correctness) | A·correctness | **NEW — top priority.** Replace the `outs_in_game` weight + appeared-in-game roster in `eb_bullpen_team_posteriors.sql` with a leakage-safe aggregate; re-train/re-eval the live home_win/run_diff/total_runs champions on the de-leaked matrix. **Named mechanism for the offline→live collapse (0.42→0.001).** ⚠️ Offline metrics will *drop* — that's correct, not a regression; validate on **live/forward + serving-parity**, not offline NLL. Standalone card, cross-linked to Epic 30.3 serving-skew. |
| 2 | **E1.8** ⭐ | **Full feature-surface leakage sweep** | A·correctness | **NEW (PM 2026-06-18).** If the #1 feature leaked, others may too — sweep all ~370 features for the same within-row/same-game peek (construction audit + serving-parity divergence + leak-signature A/B); prioritize top-importance + slim-contract features. **Could explain the broad H2H+Totals offline→live collapse.** Until done, no offline number (incl. the E1 rankings) is fully trusted. Same gotcha: de-leaking lowers offline metrics by design. |
| 3 | **E2.0** | Derivative-odds backfill (F5/team/alt closes) | B·data | Top market-data task; the totals-derivative value path; blocks the E2.6 gate. |
| 4 | **E2.2** | Dependence structure (copula) | A·market-blind | **Load-bearing, not a formality** (E2.1 note): per-side calib_80≈0.77→0.81 doesn't guarantee the *convolution* is calibrated. **Test conditioning BOTH ρ and dispersion `r` on park/run-env** — E2.1 found `r` drifts 33→8. |
| 5 | **E2.3** | Convolution → predictive distributions | A·market-blind | calib_80 ≥ 0.80 — totals un-pause + distribution UX. |
| 6 | **E5.0** | Prop market ingestion (live) | B·data | Props elevated; softest market. |
| 7 | **E5.1** | Historical prop backfill | B·data | Backtest dataset for E5.4. |
| — | **E6.7 → Slim-contract re-promote** | prune-validation gate, then re-promote | A | **Gated + now also leak-aware:** the slim **14/31/19** contracts were chosen *with* the leaky `bp_eb_xwoba` ranked #1/#2 → **re-derive the prune after E1.7's de-leak** (the importance ranking changes — coverage/uncertainty rise, the xwOBA value drops out). Then run E6.7 (per-game SHAP + stability + slice parity + PCA) before re-promoting. |

**Sessions:** Session A = per-side totals + bullpen + the slim re-promote; Session B = data ingestion (E2.0, E5.0/E5.1). **E5 pricing (E5.2+)** is the props edge test — starts once ingestion lands.

**Deprioritized by the E1 audit:** **E6.1/E6.3 generic feature work** — E1.3 delivered the redundancy finding (the slim contracts), and the audit concluded **more features ≠ edge.** ~~The one feature-investment direction that survives is bullpen~~ — **CORRECTED 2026-06-18 (E2.1b):** the bullpen "signal" was largely a **leak** (`bp_eb_xwoba` peeks at `outs_in_game`); the only real pre-game bullpen signal is **data-depth (`coverage_pct`/`uncertainty`), and it's modest.** There is **no "deepen the bullpen model" investment** to chase — the actionable item is the **de-leak correctness fix (E1.7)**, not more bullpen modeling.

**Realistic by the break:** **the production de-leak (E1.7)** landed + champions re-evaluated honestly; **totals distribution calibrated (E2.1–E2.3)** + derivative backfill (E2.0) staged; **prop data ingested (E5.0/E5.1)**. The betting-edge hope rests on **totals-derivatives + props** — H2H straight-bet edge is closed, and the apparent bullpen signal turned out to be a leak (see *Decisions*).

## Decisions & kills (on record)
- **E1 ✅ COMPLETE (2026-06-18)** — full audit arc built + validated (E1.1–E1.6); PBO/DSR + purged-CV on record → **the go-live gate is set.** Findings: **(1)** ~~no leakage in any champion~~ → **PARTIALLY OVERTURNED (see E2.1b): a within-game leak *was* present and purged CV missed it** (it guards temporal/cross-fold leakage, not a feature peeking at its own row); **(2) massively over-parameterized** — ~370 feats → **14/31/19** with no loss → re-promote on the slim contracts (**but re-derive post-de-leak — finding #3 contaminated the ranking**); **(3)** ~~bullpen EB dominates every target → clearest signal-investment direction~~ → **❌ RETRACTED 2026-06-18: that #1/#2 rank was leak-inflated** (`bp_eb_xwoba` weights by `outs_in_game`); de-leaked, it collapses to noise (0% retained). The real bullpen signal is **data-depth (coverage/uncertainty), modest**; **(4) history extension (E1.6) is a wash** → don't extend history. **Revised conclusion: the edge is the E2 per-side-totals *architecture* (honest distribution/derivatives), NOT a bullpen signal; the most valuable action E1 surfaced is the de-leak (E1.7).**
- **E2.1b ✅ COMPLETE — "gate FAIL by design" (2026-06-18)** — bullpen deepening cannot beat the incumbent because the incumbent is a **within-game leak**, proven 3 ways (leak-signature: de-leaked equal-weight 2.4582 ≈ v3 2.4571, both lose to leaky-static 2.4303 by an identical ~0.027; source `eb_bullpen_team_posteriors.sql:33`; MDA collapse #1/#2 → noise, 0% retained). **Blast radius: the leaky column is in the live home_win/run_diff/total_runs training matrices → a named mechanism for the offline→live skill collapse (corr 0.42 → 0.001), previously filed under "serving skew."** `bullpen_v3` not promoted (no real lift). Experiment B (per-reliever×handedness EB) explicitly **not** pursued (zero headroom). → **action: E1.7 de-leak.** Full detail: `E2_1b_HANDOFF.md`.
- **E3.0 ✅** built + live-validated (2026-06-17) — `feature_pregame_edge_market`.
- **E3.0b ✅** built — bookmaker drift model quantified the decay (soft books' distance to Pinnacle ~halved 2021→2025). **Commit the artifacts** (`feature_edge_book_market_era_quality`, `feature_edge_sharp_anchor_backtest`) — reusable analysis regardless of E4's death.
- **E3.1 🔴** no-edge (predict-the-move).
- **E4 🔴 CLOSED (2026-06-18)** — "bet soft toward Pinnacle": a **real, monotone CLV gradient (the program's first non-null signal)** but **too small to beat vig** (~0.5–0.9 prob-points CLV vs the ~4% soft vig) → **not cashable**; pooled ROI negative, per-season noise, totals same. Killed on **ROI net of vig** (the cashability gate); PBO/DSR not run — it can't rescue a negative (reserved for *apparent positives*). **The CLV signal still feeds the honest transparency/fair-value app surfaces (E9.11/E9.12) — just not as "+EV bets."**
- **E3.3 latency-arbitrage 🅿️ PARKED** — the only un-killed E4-adjacent thread, but a **sub-second ops/infra bet incompatible with the manual-advisory model** (a human can't win a seconds race vs a soft book's repricing) and not analyzable on 30-min snapshots. The lead-time/freshness ops work still helps CLV/transparency — not as a cashable edge.

**Strategic read:** H2H straight-bet edge is closed on **both** heads (E3.1 + E4), and now the program's apparent **#1 model signal (bullpen EB) turned out to be a within-game leak** (E2.1b) — a sobering but valuable correction that also **names the mechanism for the offline→live collapse** and makes the **de-leak (E1.7) the highest-value model-track item right now** (it may explain why honest live skill has been ~0). Remaining betting-edge hope = **totals-derivatives (E2) + props (E5)**, valued as an honest distribution/derivative *architecture* rather than any single dominant feature. Durable product value = **transparency/CLV surfaces + the fantasy vertical** (which never needed an edge). Reinforces "subscriptions, not betting profit, fund the early days" (`../gtm_strategy.md` §0).

> **Keep the H2H model live through beta (decision 2026-06-18).** "Edge closed" is a *cashability* verdict, not a retirement order. The H2H model **keeps running and serving picks through the beta phase** — it produces real tester value and the feedback loop we're learning from (write-ups, calibration, the trust/skill surfaces). We just don't frame it as "+EV straight bets." So no app surface is torn down on the E3.1/E4 close; H2H stays a first-class served model, presented honestly (model probability + CLV/fair-value, not a beat-the-book claim).

---

## Track 2 — Application build  *(one fresh session per story; beta requests prioritized)*
Ordered; the two **P1 correctness fixes lead** and can run in parallel (different surfaces). **Each story = one fresh session:** paste the **application-session bootstrap prompt** (`app_session_bootstrap.md`) first, then that single story block — build, report, end. Don't chain stories through one session.

> **🚨 APP TARGET (two live, one dead):** UI → **`frontend/` (Next.js) ONLY**; backend → **`app/backend/` (live FastAPI)**; ⛔ **legacy Streamlit UI (`app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`) — do NOT edit.** `app/` is half-alive (`app/backend/` live; rest dead). A session edited the Streamlit UI by mistake 2026-06-18; guard now in guide §0.2 + every `[App]` prompt. First action: `cat frontend/package.json` to confirm Next.js.

_This mirrors the guide's E9 backlog (§5F table). **Reconciled 2026-06-18** to add the E9 stories that were in the guide but missing here: **E9.3, E9.9, E9.10.**_

| # | Story | Title | Pri | Note |
|---|-------|-------|-----|------|
| — | **E9.15** ✅ | Fix "Model Skill — All Picks" double-counting | **P1** | ✅ **SHIPPED 2026-06-18** — one post-lineup production prediction per game (no dupes). |
| — | **E9.13** ✅ | Keep the pick write-up up to date | **P1** | ✅ **SHIPPED 2026-06-18** — write-up in sync with the served pick (+ 30.15 narrative-accuracy fixes deployed same day). |
| — | **E9.10** (A0.4.11) ✅ | Settings: profile + prefs (unblocked parts) | **P1** | ✅ **SHIPPED 2026-06-18** — new `GET/PUT /users/profile` (live; lambda deployed) backed by `credence-prod-dynamo-users`; editable `initial_deposit` persists; real email, gear-nav, sign-out-everywhere done; notif toggle = "Coming soon". **Unblocks E9.17.** |
| 1 | **E9.5** (A0.4.22) 🔄 | Password reset flow | **P1** | **CURRENT** — 🟢 READY (SES prod live); sandbox-validated; finish: branded template + redeploy + retest with a real email. Quick beta-launch win. |
| 2 | **E9.4** (A0.4.18) | Welcome email + beta onboarding | **P1** | 🟢 **UNBLOCKED (SES prod live)** — the literal gate to inviting beta users; brand the invite template + provision. Resend Path B retired. |
| 4 | **E9.2** (A0.4.34) | CLV meta-model confidence bar | P2 | Model side shipped → immediate value. |
| 5 | **E9.1** | "+EV price range" (breakeven line) | P2 | Beta request; glue on A0.4.32. |
| 6 | **E9.14** | Add Fanatics to Book Comparison | P2 | Small; unblocks fuller best-price. |
| 7 | **E9.16** | Paginate the Bet Log (~25/page) | P2 | Trivial UX win. |
| 8 | **E9.11** | Best price across top books | P2 | Builds on A0.4.32 + E9.1 (+ Fanatics). |
| 9 | **E9.17** | Bankroll-growth % + editable deposit | P2 | 🟢 **unblocked** — E9.10 shipped the `initial_deposit` field + `/users/profile` endpoint; this adds the growth-% metric on Performance. |
| 10 | **E9.3** (A0.4.31) | Live scores → Railway PG | P2 | ⬜ NEW — app + poller; poll only while games in-progress (cost guard); MLB StatsAPI fallback. |
| 11 | **E9.12** | Daily card | P2 | Needs E9.11 + E9.13 + the decision gate. |
| 12 | **E9.9** (A0.6) | Push notifications (SNS + Lambda + Web Push) | P1 | ⬜ backend BUILD; **SES email path now unblocked (2026-06-18)** — no longer SES-gated; Dagster publishes post-`predict_today`. Completes E9.10's notif toggle. |
| 13 | **E9.18** | Changelog accordion (collapsible per-week) | P3 | ⬜ NEW — pure frontend; collapse the (growing) changelog into a per-week accordion. Pairs with the Monday→Monday grouping convention (§0.2). |

**Trails its model dependency (likely beyond the window):** **E2.7** (distribution UX — needs E2.3) and **E5.5** (prop pages — needs E5.2/E5.3). The §0.3 app surfaces (E2.7, E4.6, E5.5) get their prompt emitted by the upstream model session.

**Parked but accounted-for (not lost — see *Out of scope*):** **E9.7/E9.8** (A0.6B OAuth → A0.7 Stripe) = the **GTM/paid-tier track** (`../gtm_strategy.md`); **E10.1** (master 34.1, parlay *calculator*) = parked under E10 — but it's honest-value-now / zero-edge-required and beta-friendly, so it's a **candidate to pull into this window** if you want a differentiation win before the break (flag it and I'll slot it).

---

## Cross-track dependencies
- **E1.5 + PBO/DSR (Track 1) gate go-live** of every betting strategy app-surface (E9.12 daily card, any "+EV" framing) — the app builds the views, but they go live honestly only once the gate clears.
- **E9.12 (daily card)** consumes the decision gate + **E9.11** (best price) + **E9.13** (fresh write-up) → keep it after them.
- **E2.7** needs **E2.3**; **E5.5** needs **E5.2/E5.3** — app surfaces trail their model work.
- App-prompt handoff (§0.3): app surfaces marked 🧩 are unblocked only when the upstream model session has emitted their prompt.

## Out of scope for this window (parked until after the break)
- **Multi-sport** (NFL / NCAAF / NCAAB) — the fall push; see `../../multi_sport_roadmap.md`.
- **Fantasy / Dynasty vertical** (F1–F8) — baseball, but a separate vertical + the larger build; resumes after the break and is gated on **E7** (MiLB MLEs) for prospects. *(Pull it into Track 1 if you decide it's a pre-break priority — flag it.)*
- **E5.2–E5.6** (prop pricing/gates/DL), **E6.2–E6.5**, **E7** (MiLB), **E10** (parlay — **except E10.1/34.1, the honest calculator, which is a Track-2 pull-in candidate, above**), **E11** (dbt→lakehouse migration), **E9.7/E9.8** (A0.6B/A0.7 OAuth/Stripe — the **GTM track**, tracked in `../gtm_strategy.md`).

## Maintenance
This is the persisted mirror of the Trello ordering. Update it when a story ships, a beta request lands (it enters Track 2 via the E9 backlog), or the gate verdicts change (e.g. if E4.3 comes back no-edge, the H2H edge story closes and the app track leans fully into transparency/CLV surfaces). Re-window after the All-Star break (multi-sport + fantasy come into scope then).
