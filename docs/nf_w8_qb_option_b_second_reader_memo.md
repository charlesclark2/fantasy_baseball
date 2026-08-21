# NF-W8 — QB Option-B Consumption Decision · Second-Reader Review Memo

**Date:** 2026-08-20
**Prepared by:** PM (Claude)
**For:** the independent second reader (operator, or a designee)
**Status:** ⏳ SIGN-OFF PENDING — this flag is currently blocking NF-W8 (the weekly cross-position optimizer input) regardless of any other work.

---

## 0. Why this memo exists, and who the reviewer should be

NF-W7f raised a governance second-reader flag when it produced a QB weekly distribution that is the **best-calibrated and best-scoring construction on record** but **failed the `dsr_ok` certification gate**. The flag was carried forward through NF-W7j and NF-W8-0 / 0b / 0c and remains **open**. It exists to guard against the one failure mode this program most fears: **adopting a decision *because* a gate failed** (the E2.1-r inversion).

⚠️ **Independence note — read first.** I (PM) made the original Option-B call, and it was registered forward in `ablation_results/nf_w8_0_preregistration.md §1`. That makes me the **advocate** for this decision, **not** the independent voice the flag calls for. This document is therefore a **review packet** for an independent reviewer to run — not a self-signed approval. My own position is stated plainly in §10 and should be read as the interested party's, not the reviewer's.

---

## 1. The decision under review (Option B)

**Option B, as registered:** `dsr_ok` (deflated-Sharpe certification) is a **shipping gate**, not a **consumption bar** for a projection product. NF-W8 therefore **consumes** NF-W7f's recalibrated QB distribution (`zm_floor`) as its QB generator, under a registered, caveated, second-reader-flagged decision — **without relaxing the ship bar**.

**What it explicitly is NOT:**
- It is **not a re-certification** of the `zm_floor` run. The certification standard and the `dsr_ok` gate are untouched.
- It is **not a relaxation** of `dsr_ok` for anyone. No threshold moves.
- It is a **consumption** choice, scoped to a deploy-held, `best_alpha=0`, NF-G0 challenger. Nothing serves.

---

## 2. The critical governance check — E2.1-r provenance

This is the load-bearing item. **Option B must be a forward decision, not a post-hoc rationalisation of a failed gate.**

- **Claim:** Option B was pre-committed in `nf_w8_0_preregistration.md §1` **before** the NF-W8-0 smoke or decisive run existed.
- **How to verify (reviewer action):** confirm the §1 registration's commit timestamp predates the NF-W8-0 run artifacts (`git log` on the prereg file vs the `nf_w8_0_*.json` mtimes / commit). If the registration predates the run, the E2.1-r concern is satisfied on provenance.
- **Corroborating discipline:** every successor since (NF-W8-0b, 0c) has **left its verdict state exactly as registered** even when the run outcome was more favourable than the registered fall-through prose (NF-W8-0c's `cond_shift` actually *closed* the gap yet the flag stayed `false`). That is the behaviour of a team honouring pre-registration, not gaming it.

---

## 3. Why `dsr_ok` is arguably the wrong gate for a projection *consumer*

- `dsr_ok` (deflated Sharpe) is a **betting-posture deflation gate**: it asks whether a winner would survive the selection bias of an **edge search** (was it cherry-picked from a field of trials?). It exists to stop a spurious *edge* claim.
- A **projection product** with `best_alpha=0` makes **no edge claim**. Its product-relevant questions are: *is the distribution calibrated?* (PIT) and *is it a good proper score?* (CRPS).
- On those questions, `zm_floor` is unambiguous: the **only** QB construction clearing the PIT bar (0.0281, 8/8 folds vs the incumbent's 0/8) **and** the best-scoring (+0.0184 CRPS vs the matched foil; +0.0189 vs direct_points). Every alternative is strictly worse on **both** axes.
- So the product's own gates say *yes*; the gate that fails (`dsr_ok`) is answering a question — "would this survive an edge search?" — the product isn't asking.

---

## 4. What signing off does — and does NOT — unblock (scope)

**IN scope of this sign-off:** NF-W8 may consume the `zm_floor` QB **distribution** (a distribution-level consumption choice).

**NOT resolved by this sign-off:**
- The **cross-position level gap** (NF-W8-0 / 0b / 0c) is a *separate* blocker. Raw-point cross-position surfaces (start/sit, lineup totals), superflex, and the optimizer's cross-position comparability stay **blocked** pending NF-W8-0d (the gate-design/power instrument) → NF-W8-0e (the QB|passing_yards substrate fix). Option B is about *which QB distribution to consume*, not about *putting QB on one scale with WR/TE/RB*.
- **VOR-ranked boards in standard 1-QB leagues are unaffected either way** — the replacement-level shield (measured 0.000 rank moves at NF-W8-0) holds regardless of this decision.

⇒ Signing off **unblocks NF-W8's use of the QB distribution**; it does **not** declare cross-position comparability solved.

---

## 5. New facts since the flag was raised (NF-W8-0b / 0c) — they strengthen the case but don't change the decision

- The QB defect is now **confined to one per-stat cell** (QB|passing_yards conditional level, ~93% of the model channel) — bounded and understood, not diffuse.
- NF-W8-0c's `cond_shift` arm **closes** the cross-position gap and **passes 7 of 8 registered clauses** (PIT 7/7, better than incumbent; CRPS unharmed; beats the permuted foil; both degenerates lose; PBO 0.0) — refused by `dsr_ok` **alone**. This is the **4th** QB story refused by `dsr_ok` alone, which is why NF-W8-0d will test whether the gate itself is mis-specified for weekly QB effects of this size.
- These facts make the distribution look *more* trustworthy (the flaw is a single, understood cell; the machinery is sound). They do **not** alter the Option-B question, which is purely: *may a projection consumer use the best-calibrated, best-scoring construction despite a failed deflation gate?*

---

## 6. The case *against* / risks the reviewer should weigh

- **Precedent.** "Consume, don't certify" is a judgment about which gates bind for which consumers. Even correctly scoped, it opens a door; the reviewer should be satisfied the framing is principled (a deflation gate vs a calibration/score gate) and not a slippery one.
- **Weaker-footing rows.** QB rows are explicitly *not* certification-equivalent to WR/TE/RB. A downstream surface that fails to carry the caveat could present a caveated QB number as equivalent.
- **A near-future contingency.** NF-W8-0d may show the gate *is* clearable at a feasible design point — in which case the cleaner path is simply to clear it, and the "consumer gate" framing becomes less load-bearing. That's a reason to keep the decision **reversible**, not a reason to block it now (NF-W8 is blocked today and 0d is not yet run).

---

## 7. Caveats and reversibility already in place

- A caveat **rides every QB row** the layer emits: *"calibrated + best-on-record, consumed under Option B; not certification-equivalent to WR/TE/RB."*
- The decision is recorded **on the module** and **on every verdict** the harness produces.
- **Deploy-held, `best_alpha=0`, NF-G0** — nothing serves; no user sees a QB number because of this. The decision is a **research-consumption** choice and is **fully reversible**.

---

## 8. Sign-off checklist (the reviewer answers these)

1. **Provenance (E2.1-r):** Is Option B registered *forward* — the §1 registration predates the NF-W8-0 run artifacts? ☐ yes ☐ no
2. **Gate applicability:** Do you agree `dsr_ok` is a betting-posture/deflation gate rather than a projection-consumer gate, so a `best_alpha=0` projection may gate on PIT + CRPS instead? ☐ yes ☐ no
3. **Ship bar intact:** Is the certification standard genuinely untouched (this is consumption, not re-certification)? ☐ yes ☐ no
4. **Caveats:** Are the per-row / module / verdict caveats in place, and will every downstream QB-derived surface carry them? ☐ yes ☐ no
5. **Scope:** Is the sign-off correctly limited to *distribution consumption* and does NOT imply cross-position comparability is solved? ☐ yes ☐ no

---

## 9. Sign-off block

- ☐ **APPROVED** — NF-W8 may consume `zm_floor` QB under Option B (caveated, deploy-held).
- ☐ **APPROVED WITH CONDITIONS:** ______________________________________________
- ☐ **REJECTED / NEEDS MORE:** ______________________________________________

Reviewer: ____________________  Date: ____________

---

## 10. PM position (the advocate's view — not the independent sign-off)

For transparency: I made the original Option-B call, so this is the interested party's assessment, not the independent review.

I believe Option B is sound: it was registered forward (the E2.1-r concern is answered on provenance), the product's own gates (PIT, CRPS) both pass decisively, `zm_floor` is the best construction on record on both, the failing gate answers a question the product doesn't ask, and the decision is caveated, deploy-held, and reversible. NF-W8-0b/0c only sharpen this — the flaw is one understood cell.

But because I am the advocate, the sign-off should be an **independent** yes/no against the §8 checklist — run by you, or handed to a fresh engineering session / human reviewer with no stake in the original call. If you'd prefer maximal independence, I can hand this packet to a clean review session instead of you signing it directly.

**Recommended next regardless of the outcome here:** NF-W8-0d (the gate-design/power instrument) before NF-W8-0e (the substrate fix) — agreed. If 0d shows the gate is clearable, this whole consumption question may become moot.
