# NF-INJ4b — closeout: `SHIP_CANDIDATE`, **deploy-held**. Nothing serves.

**`best_alpha = 0`. The served Questionable / Doubtful / Out availability discount is still EXACTLY
ZERO**, no production caller passes the designation channel, and the publish decision is the
operator's.

| record | what it is |
|---|---|
| `nf_inj4b_preregistration.md` | the fresh registration, committed before any arm was scored |
| `nf_inj4b_substrate_vintage.json` | the substrate rebuild + the vintage check that makes the honesty clause admissible |
| `nf_inj4b_designation_duration.{json,md}` | the decisive run |
| `nf_inj4b_counterfactual.{json,md}` | the ship path's counterfactual + the operator packet |
| this file | the verdict, the findings, and what the operator does next |

---

## 1. ⛔ The verdict, with its honesty clause attached — they are not separable

**Nine of nine registered gates pass and the study ships, subject to the deploy hold.** That was the
expected outcome and the pre-registration said so forward, in §5, before the run.

**This study bought a PROPERLY-REGISTERED RECORD of an ALREADY-MEASURED result.** The field, the
folds, the seed and the substrate are NF-INJ4's; **34 of 34 published figures reproduce** at the
artifact's own 6-decimal resolution. ⛔ **It is not new evidence, not a replication, and not fresh
confirmation.** A re-run that reproduces a known number confirms the pipeline, not the hypothesis.

What it *does* say: the mechanism's evidence is now held under a registration whose anchor clause
measures an **arm property** rather than a **fold size**, so the refusal that blocked it no longer
stands in the way.

⛔ NF-INJ4's registration, verdict and record stand **unedited**. This superseded ONE clause going
forward and never re-read the refusal (E2.1-r).

**"Unchanged" was a measurement, not an assumption.** The field/folds/seed are IMPORTED from
NF-INJ4's module, so there is no second place for them to drift; and because NF-INJ4's frame is
gitignored and absent from a fresh worktree, the substrate was rebuilt through NF-INJ4's own census
loaders and checked against its committed census — 1,309 rows / 398 players / weeks 1–18, cells
842/239/199/29, PIT 1,309 checked and 0 dropped, **identical on every field**. ⭐ The rebuild wrote
only the parquet: `run_nf_inj4_census.main()` writes its report at fixed paths and running it would
have overwritten a decided story's audit trail.

---

## 2. The one clause that changed, and how it was registered

`oracle_respected` — *"no arm beats its own-form oracle"* — measured the ORACLE'S SAMPLE SIZE: the
peek is fitted on ~131 test rows against arms trained on ~1,178, a **9.0× ratio fixed by the CV
design**. Both readings of that one measured pair are now registered as **separately named clauses**,
because registering one does not give you the other:

| clause | reading | result |
|---|---|---|
| `anchor_pair_informative` | NF-W6d — could the pair ACT at all? | ✅ 4 of 7 pairs ACTIVE (3 shippable) |
| `oracle_floor_matched_resolution` | NF1.9 (f) — does the floor HOLD at equal family AND equal resolution? | ✅ holds 7/7, **4/4 non-vacuously** |

⚠️ The floor is **vacuous on an INACTIVE pair**, so its non-vacuous count is published beside the
activity count (NF-D20). The tie tolerance is measurably not load-bearing — the smallest active
margin is 0.0147, about **14,705×** the ±1e-6 band, and every inactive pair is an exact tie.

The **retired naive clause is still reported** and still reads FALSE on all three shippable arms.
In this design an arm beating its own peek can only be CAPACITY — leakage is excluded by the fold
construction (disjoint by player), not by the anchor. ⚠️ That does not generalise.

Both anchor clauses were declared **injection-invariant forward** — the declaration NF-INJ4 said
belonged to its successor. The ladder did not refute it, and that is reported as **consistency,
never as a passed check**: a clause that passes at every rung has nowhere to move upward, so the
ladder could only ever refute.

---

## 3. ⭐ The findings — what was genuinely new

### 3a. The positive control returned `VACUOUS`, and the badge is a specification artifact — measured

The badge **stands exactly as the instrument returned it**. The claim behind it was MEASURED rather
than argued: on payloads where the mechanism is genuinely ABSENT (designations shuffled, 5 seeds,
every marginal preserved) **zero arms survive** and five gates fail every time. **The gate family
does not certify noise.**

⭐ **The instrument finding, general rather than local.** With `inject(0.0)` defined as the IDENTITY,
the null-control leg is **logically equivalent to the negation of the ship verdict**: `VACUOUS` fires
exactly when some arm clears every gate on the null payload, the null payload IS the real data, and
the study ships exactly when some arm clears every gate on the real data. ⇒ **ships ⟺ `VACUOUS`.**
For any caller defining `inject(0) = identity`, that leg carries **zero information about the gate
family**.

⭐ **And NF-INJ4's clean null leg was clean for the WRONG REASON** — which is why this could not have
been seen before. It recorded `null_control_survivors: []`, but its `oracle_respected` clause was
FALSE on the real payload, so it blocked every arm on the identity payload too. **The defective
anchor was masking the mis-specification**, and removing it is what exposed it. ⛔ NF-INJ4's verdict
stands; this is drawn from its own published figures.

⚠️ **A defect in THIS registration, reported as one.** The pre-registration predicted the control's
PBO leg would be inert and said nothing about the null leg, whose identity-at-zero specification it
inherited verbatim and never examined. ⛔ The remedy — a MECHANISM-ABSENT null payload rather than an
UN-INJECTED one — is a forward decision, not adopted here after seeing the badge.

### 3b. Three counterfactual defects, all caught by controls rather than by review

⭐ Each was invisible to the scope-gated run (which is correctly a no-op today) and would have
reached the operator as a wrong answer:

1. **The no-op control failed first time** — 1,715 of 1,716 rows "moved" under an EMPTY designation
   map, because the board key is `(config_name, n_teams)` and not `config_name`. Every rank move in
   the packet would have been an artifact of concatenating a 10-team and a 12-team board.
2. **A silent label-case mismatch made the discount a complete no-op** — the feed emits
   `Questionable`, the model's levels are lower-case, so `.map(...).fillna(1.0)` resolved every
   multiplier to NaN and applied nothing: 89 designated players on the board, zero ranks moved, no
   error, and an id-join coverage reading a healthy 89. **A join-coverage check cannot see a
   LABEL-KEY defect** any more than an id-keyed check can see an id one. An unmapped label now
   REFUSES rather than defaulting to 1.0.
3. **The magnitude table priced the REGISTERED arm rather than the CERTIFIED WINNER** (out ×0.8682
   against the certified ×0.8639). The winner is now read out of the decisive run.

⭐ **The transferable lesson: a scope gate that refuses every row leaves the whole leg unexercised.**
The out-of-scope rehearsal is what surfaced all three; without it the operator's Week-1 invocation
would have been this code's first-ever execution against real producer output.

### 3c. The counterfactual is INACTIVE today, and that is uninformative

Measured: the 2026 regular season starts **2026-09-09** (from the schedule) and the live feed carries
**119 Questionable, zero Out, zero Doubtful** — the preseason shape. The registered
regular-season-only scope rule refuses all 119, so the counterfactual is exactly a no-op. ⛔ **That is
not evidence the discount is small, and it is not a passed check.** The value arrives with the
Week-1 report.

For magnitude: the rehearsal moves **453–491 ranks per board** on a `questionable` cut alone (max 37
— DK Metcalf 96→133). `out` is ×0.8639, roughly four times that cut, so the in-season effect will be
materially larger.

### 3d. ⭐ A FOURTH way a red proof lies — a renamed guard reads as a perfect RED

Found by running **NF-INJ4's own red proof** after this story renamed one of its guards: it kept
reporting **14/14 RED with one case pointing at a test that no longer exists**. `pytest` exits
NON-ZERO on an unresolvable node id, and both red proofs read a non-zero exit as "the guard caught
it" — so a guard that has merely been **renamed, moved or deleted scores a perfect RED forever**.

That joins the three already documented: the mutation never LANDS (#682), it lands but does not MOVE
the asserted predicate (#815), it lands on the WRONG symbol (E11.24 `prediction_log`). Both proofs
now assert every named node id RESOLVES. ⚠️ The probe belongs in the **baseline** phase, not
per-mutation: a mutation that trips a module-level assertion legitimately breaks collection, and
probing there turns a working RED case into a hard error (it did, on first cut).

Re-anchoring the stale case then exposed **two further real defects**, neither visible from a green
suite:

1. **The case's MUTATION was stale too** — it wired the model into the serving owner, which the OLD
   absence guard forbade and the new presence guard permits *by design*. Re-anchored onto the
   property that now holds: a PRODUCTION CALLER passing `designation_games=` must go red. A guard's
   mutation moves with it; it is not deleted (MH2.7).
2. ⭐ **With the mutation re-anchored the guard STILL stayed green**, because its caller scan
   resolved the repo root one level too HIGH — `rglob` matched NOTHING, the loop never ran, and the
   guard passed on an **empty set** while appearing to certify the whole production tree
   (DSR-CONV #690: a guard that ITERATES matches must assert the match set is non-empty). Fixed,
   with a non-vacuity assertion on the file count; and the scan no longer exempts
   `season_projection.py` itself, since a serving caller defined INSIDE the availability owner lifts
   the deploy hold exactly as one outside it does.

### 3e. The 2026 capture dependency is still open

`nfl/pit/injuries` holds **12,136 rows, all season 2025, from exactly ONE capture date (2026-08-05),
and ZERO rows for 2026** — unchanged since NF-INJ4 measured it. **The NF-W0a capture has fired once,
ever.** The 2026 re-test and every downstream monitoring use depend on it running weekly. Operator
lane; named so the re-test trigger is not the actively-misleading kind.

---

## 4. What was wired, and why the deploy hold is now structural

`compose_availability_caps` is wired into `apply_availability_chain` as an optional
`designation_games` callable, defaulting to None, and the absence guard flipped to a PRESENCE guard
in the same commit.

- The two channels **compose as a single strongest min-cap from one baseline**, never sequentially:
  two rate caps applied in sequence compound to **7.83** where the composed answer is **9.06** on the
  registered both-channels row — the stacking the NEWS-1 rule exists to prevent, through a third
  channel that rule predates. The designation cap stamps `_formal_discount_applied` so the news
  channel stays disjoint.
- ⛔ **The hold is structural, not a flag.** With the argument absent, `new_games` is `formal_new`
  itself, so the pre-NF-INJ4b path is preserved by construction; and **no production caller passes
  the argument**, which a guard measures across the whole tree. The old guard could only say the code
  was absent — this one says the **served board does not move**.

---

## 5. ⏭️ Operator steps — all post-merge; the publish decision is yours

⛔ Nothing below is required for the merge, and none of it changes what is served today.

**A. From Week 1 (2026-09-09 onward) — the counterfactual becomes a real read.** LAPTOP:

```
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
  quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_counterfactual
```

Once in scope it emits the real per-config top-25 moves (including superflex) into
`ablation_results/nf_inj4b_counterfactual.{json,md}`. Read §3 (the no-op control) first — if it does
not pass, no number in the packet is trustworthy.

**B. The capture-pinned rebuild**, which this story deliberately did NOT do: the registered ship
path's step 1 is a full board rebuild against a pinned baseline with matched market vintages, and
that is what produces the publish-candidate board. It needs a serving caller to pass
`designation_games=`, which is the moment the deploy hold is lifted, so it is yours to authorise.

**C. If it ships, two things become due in the same change**, and both are named rather than assumed:
- `test_nf_c9_designation_disclosure.py` is re-anchored onto the new implementation (never weakened
  — MH2.7); and
- **NF-C9's user-facing copy** — *"our projected-games figure does not take this into account"* —
  becomes **FALSE the moment the discount is live**, on every surface that renders it.

**D. `nfl/pit/injuries` needs to be running weekly** for the 2026 re-test to be reachable (§3d).

