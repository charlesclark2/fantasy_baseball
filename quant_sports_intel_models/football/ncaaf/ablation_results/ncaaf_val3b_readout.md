# NCAAF-VAL3b — the cold-start μ_total correction as ONE pre-registered contrast

**Verdict: `SHIP_CORRECTION` — and it is `DEPLOY-HELD`.** The contrast clears every pre-registered
gate; the train/serve parity check that gates a pre-opener ship **FAILS on 2 of 3 legs**, so nothing
serves. Market-blind · `best_alpha = 0` · no serving write, no registry edit, no refit of a served
artifact, no bet.

_Pre-registration: `ncaaf_val3b_preregistration.md` (committed before a single arm was scored).
Machine record: `ncaaf_val3b_single_contrast.{json,md}`. Parity: `ncaaf_val3b_serve_parity.json`.
Cache re-assembled 2026-08-23 · 8,325 games / 4,187 closes · 6,024 OOS games · 8 purged folds
2018–2025 · served `ridge`/`strength_pace`/`strength_posterior`._

---

## 1. What was asked, and what was actually at issue

VAL3 measured a real cold-start bias — the served μ_total runs **+2.074 pts hot in weeks 1–3** — and
a correction that removes 73 % of it on **8/8 folds**, clearing every ship clause. It was refused by
**PBO 0.5300**, and it MEASURED why: the **two-arm** decision PBO is **0.0000** while the
**eligible-set** PBO is **0.7010 — worse than the full field**. That is the signature of four
near-identical correction forms, not of an unstable winner. The remedy sanctioned by MH2.2 /
NF-W6b-C / NCAAF-P2.1-S1 is a **fresh FORWARD registration of a coherent family**, never a post-hoc
trim. VAL3b is that registration, and the family has two members.

## 2. The contrast

| arm | δ̄ (pts) | CRPS wk1-3 | gain | folds won | DSR | p | C1–C8 | M1/M2 |
|---|---|---|---|---|---|---|---|---|
| `none` (foil) | 0.000 | 9.4642 | — | — | — | — | — | — |
| **`bucket_shift`** | 1.517 | **9.3793** | **+0.0848** | **8/8** | **0.9996** | 0.0047 | ✅ | ✅ |

Cold-start bias **+2.074 → +0.557 pts**; pooled **+0.362 → +0.102**. Per-fold improvement is
positive on every fold (2018 +0.0085 … 2025 +0.1433) and the arm wins **8 of 8** fold flips.

**The descriptive market read** (715 close-carrying cold-start rows; over actually hit 0.457).
⚠️ DESCRIPTIVE — never a clause, never an edge claim, and the estimator never sees it (C4). Produced
by the **`_clv_leg`-immune `over_tilt_report`** — a `game_id` join that takes no positional index
into any array. ⛔ Not `_clv_eval` (the reset_index row-misalignment INC).

| arm | model → over | mean μ − close |
|---|---|---|
| `none` | 0.614 | +1.370 |
| `bucket_shift` | **0.502** | **−0.144** |

## 3. The one question a reader should ask first — and it is answered with a number

A successor whose declared field is **smaller** than its parent's invites exactly one suspicion:
*did the arm clear the gate, or was the gate lowered?* The bar **is** lower — VAL3b's `SR0` is
**0.18376** against VAL3's **0.35374** — and the pre-registration says so in those words before any
score. So the question was answered by **re-scoring the arm under VAL3's own recorded bar**, and
under the strictest combination constructible from either study's declared quantities:

| reading | n_trials | `V` | SR0 | DSR | clears ≥ 0.95 |
|---|---|---|---|---|---|
| **VAL3b, declared forward** | 2 | 0.12500 | 0.18376 | 0.999627 | ✅ **BINDING** |
| VAL3's full-field `V` | 8 | 0.05878 | 0.35373 | 0.997713 | ✅ |
| VAL3's DSR-CONV variant | 8 | 0.09080 | 0.43965 | 0.994832 | ✅ |
| strictest constructible | 8 | 0.12500 | 0.51584 | 0.989932 | ✅ |

⭐ **The lowered bar did no work.** The arm clears DSR at every admissible reading, including two
that are *harsher than anything either study declared*. DSR was never the binding gate in VAL3
either (it recorded 0.998). **PBO was the sole refusal — and PBO is precisely what a single
pre-registered contrast removes by construction, not by relaxation.** ⛔ This table is
NON-BINDING and changes no verdict; reading a null off a sensitivity after the binding gate failed
would be the E2.1-r inversion (NF-D15 g″). It is reported because it can only make the record
stricter.

## 4. Gates

- **PBO / CSCV — `INAPPLICABLE`, and no number is computed.** A single pre-registered contrast has
  no search to overfit. `cv_power.classify_null`'s `n_arms < 2` branch (the MH2.7 co-fix) says
  exactly this and emits no re-test trigger. ⛔ Recorded INAPPLICABLE, never "passed", and the
  two-arm CSCV figure is **deliberately not reproduced here** — VAL3 already reported it as a
  labelled lower bound, and repeating it inside the successor's own gate block would read as *"the
  gate we failed now passes"*, which is the misreading this shape exists to avoid.
- **DSR 0.9996** ≥ 0.95; SR 1.2519 vs SR0 0.18376; ceiling at 8 folds **0.99991**, so the gate is
  REACHABLE at this design (MH2: at 3 observations it is not).
- **BH** — one hypothesis ⇒ cutoff **is** α = 0.05; p = 0.0047 ✅. Stated so a reader sees the
  multiplicity correction became trivial as a *consequence of the declared design*, not because it
  was switched off.
- **Fold consistency** (`cv_power.fold_consistency_clause(8)`): 6 required, **8 attained** ✅;
  calibrated false-fire 0.1445 (the legacy 60 % clause would ask 5 at 0.3633).
- **C1–C8 all ✅** — and they are the **PARENT's function, called**, not a copy: pooled PIT
  0.02606 → 0.02691 against a +0.0020 tolerance; pooled `calib_80` 0.8086 and cold 0.8302 against a
  0.78 **floor** (never a target); `wk4+` CRPS gap **0.0**; σ checksum gap **0.0**; C8 **FLOORED**
  with the anchor pair **ACTIVE** (peek 9.3464 vs its matched-n control 9.4154, so the peek genuinely
  bought something and the floor is informative — NF-W6d).
- **Instrument control** — closed-form vs ensemble CRPS on the foil: 5,000 draws 0.02125 → 20,000
  draws 0.01234, i.e. **it converges** (0.130 % of the CRPS). Read the convergence, not the gap.

## 5. Materiality — closing the gap VAL3 recorded and handed forward

VAL3 recorded that it had pre-registered a band in POINTS but no practically-meaningful CRPS effect,
so `classify_null` correctly fell through to its honest default — *"a pre-registration gap, and a
successor registers it forward."* Both bars below **BIND**, both are **stricter** than VAL3's clause
set, and both have **zero free parameters**.

| bar | required | observed | ok |
|---|---|---|---|
| **M1** — wk1-3 \|bias\| reduction (VAL2's inherited 1.0-pt band) | ≥ 1.00 pts | **+1.517** (+2.074 → +0.557) | ✅ |
| **M2** — relative wk1-3 CRPS gain | ≥ **0.7543 %** | **0.8962 %** | ✅ |

M2 is a closed-form function of two constants VAL2 recorded *before VAL3 existed*: its 0.15 σ
cold-start bias and its 1.0-pt band (= 0.065 σ). For a calibrated Gaussian the expected CRPS is
`σ·E[g(Z)]`, `Z ~ N(−β,1)`, so the **relative** gain is σ-free: `C(0.150) = 0.57053077`,
`C(0.085) = 0.56622711` ⇒ **0.7543 %**. Removing the bias entirely is worth 1.1115 %, so M2 asks for
**68 % of the whole available headroom**. `verify_m2_derivation()` recomputes it at run time and
HALTs if the literal drifts — a bar that exists only as a literal is a bar nobody can reproduce, and
this study's author had already read the parent's scores.

**Detectability.** `cv_power.mde_in_sd_units(n_folds = 8) = 0.95` fold-delta SDs at 80 % power; the
observed lift is **1.252 SDs — above the MDE**, so the design could see an effect of this size and
did.

## 6. What this study does NOT do, stated because each is a real cost

- ⛔ **It does not re-attribute the channel.** VAL3's matched foils (`week_blind`, `pooled_level`)
  are honest, in-principle-shippable estimators; keeping one as a "diagnostic" to hold it out of the
  multiplicity count would be exactly the laundering MH2.2 forbids, so they are **out of the field
  entirely**. The attribution is **CITED** from VAL3 §4b — magnitude `bucket_shift − week_blind`
  **+0.0704, 7/8, p 0.0051**; scoping `week_blind − pooled_level` **+0.0000, 3/8, p 0.4928** — not
  re-measured here.
- ⛔ **It cannot discover a better form.** That is the point, not an oversight: there is nothing to
  search, which is what makes PBO inapplicable.
- ⛔ **No δ-scaling.** `over_scale` topped VAL3's raw leaderboard, but its PAIRED read is a **TIE**
  (+0.0070, 5/8, p 0.779) and it was BEATEN by its own-form peek. A rank cannot tell a tie from a
  win (NF1.8); a magnitude adopted after seeing it rank is the inadmissible-λ shape.
- ⛔ **The +0.557 pt residual is not touched.** The estimator cannot track a rising level; that is a
  separate lead (a drift-aware estimator), deliberately not bundled.

## 7. Ship gating — the parity check FAILS, so this is DEPLOY-HELD

The spec permits a pre-opener ship only if the S1-serve-class train/serve parity holds **against the
SERVED artifact contract, checked directly**. It was — by reading the artifacts and the serving
code, never from memory (`ncaaf_val3b_serve_parity.py`). **2 of 3 legs fail ⇒ DEPLOY-HELD.**

| leg | ok | the gap |
|---|---|---|
| **(i) expressibility** | ❌ | `ncaaf_game_mean_v2.json` is a **pure linear coefficient table** — 17 fields, none a week/shift/cold-start term — and `NcaafGameMeanParams.predict(self, values, target)` **receives no week at all**. A week-conditional δ is **not expressible in the served contract**. Serving it needs a NEW field (e.g. `cold_start_shift_total` + `cold_start_max_week`) *and* a `predict` that takes the week: a contract change with its own schema bump, not a coefficient refit. |
| **(ii) quantity** | ❌ | The study validated **8 per-fold in-fold δ's spanning 1.291–1.909 pts** (spread 0.618). The served mean is **one full-history refit** (8,325 rows, 11 seasons), so the δ that would ship is a **ninth estimate** appearing in no fold of this study and never scored out of sample. Every per-fold δ is honest; the *served* one is a different quantity — E7.9 train/serve consistency. The estimator is deliberately in-fold, so a full-history δ is **not** the mean of the eight. |
| **(iii) week column** | ❌ | `game_prediction_snapshot.py:696` assigns `df["season_order_week"] = df["week"].astype("int64")` — a **verbatim alias of CFBD's raw `week`**, added (per its own comment) only to satisfy a frame contract and documented as UNUSED. CFBD restarts `week` at 1 for the postseason (P1.1 / P0.6b), so the serving frame carries the study's column NAME with the **restarted** values: an implementation keyed on that name would apply a cold-start correction to **bowl and playoff games** — silently, on the highest-profile slate of the year — while **looking correct in review**. The honest column lives upstream in the P1.3 `feature_pregame_matrix`; the serving path must carry it through and the alias must go. |

⚠️ **Leg (iii)'s first implementation was a substring check (`col in source`) and it returned a
FALSE PASS** — satisfied by the alias assignment itself, and by the warning comment above it. A
name-match cannot tell a column from an alias of the column it forbids. The AST version is the fix,
and the near-miss is recorded because it *is* the finding (NF1.7 (a) / INC-38).

⇒ **Recommendation: `DEPLOY_HELD`.** Ship post-opener via the P1.4 serve path once (i)–(iii) are
closed. **Nothing serves from this session's hands.**

## 8. Reproduction

The population reproduced **exactly** on a fresh `--assemble`: 4,187 closes / 6,024 OOS games /
folds 2018–2025, all three **binding** pin legs ✅. `cache_assembled_at` is **reported, not pinned** —
declared forward in §7 of the pre-registration, because `assemble_cache` stamps `date.today()` and
that leg would fail for a reason carrying no information about the population while burying the
three legs that define it.

⭐ Worth noting on its own: VAL3b re-ran the contrast **from scratch on a re-assembled cache a day
later** and reproduced VAL3's CRPS to four decimals (9.4642 / 9.3793) — an independent reproduction
of the parent, not a re-read of it.

**Guards.** `betting_ml/tests/test_ncaaf_val3b_single_contrast.py` (29 tests), **RED-proven 27/27**
by `ncaaf_val3b_red_proof.py`. The proof found **four vacuous guards** on its first pass and all four
are fixed: M1 accepted a **sign flip past zero** as a bias reduction; M2 could have been an absolute
gain (re-introducing the scale dependence its derivation exists to remove); the in-fold check was a
name-match that `fold.eval_year + 1` sailed through (the E11.24 #815 "landed but didn't move the
predicate" class); and the NAMED-implementation guard was satisfied by the *reader's* mention of a
key the *writer* had stopped emitting (NF-C0e wired-vs-invoked).
