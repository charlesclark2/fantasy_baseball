// NF-C-LDA-1 — regenerate the OPTIMIZER PARITY FIXTURE from the SHIPPING engine.
//
// ══ WHY THIS EXISTS ═══════════════════════════════════════════════════════════════════════════
// There are two draft optimizers: `frontend/lib/draft-optimizer.ts` (the shipping engine, which the
// web app runs) and `quant_sports_intel_models/fantasy_engine/draft.py` (which the API Lambda runs
// for the live-draft extension). Both headers claim lock-step. They had SILENTLY DRIFTED: measured
// 2026-08-19, the Python engine was two shipped fixes behind — the NF-D19 tier sizing and the
// NF-C2.1 flex-seat re-basing — and on a real 2026 full_ppr/12 board that changed WHICH PLAYER was
// recommended (5 of 8 slots agreed in one mid-draft state).
//
// Nothing surfaced it. Both engines run, both return plausible recommendations, no error anywhere —
// the E9.61 "two renderers of one field are two rule sets" class, on the thing the product advises
// with. So the drift is made a BUILD FAILURE: this script runs the TS engine over a fixed board and
// a fixed set of draft states and records what it returns; `betting_ml/tests/
// test_nf_c_lda_1_optimizer_parity.py` asserts the Python engine reproduces those bytes.
//
// ⭐ THE TS SIDE IS THE AUTHORITY, DELIBERATELY. It is the engine users already draft with, and its
// two extra fixes were each measured on live boards. Parity is restored by moving Python to it,
// never the reverse — and this file is what makes that direction structural rather than a habit.
//
// ⚠️ THE FIXTURE IS REAL ENGINE OUTPUT, NEVER HAND-WRITTEN (NF-C0e). Regenerate it — do not edit it
// — whenever the TS engine's behaviour changes ON PURPOSE, in the SAME commit as the Python change
// that follows it:
//
//     node --experimental-strip-types frontend/scripts/gen-optimizer-parity-fixture.mjs
//
// (Node >= 22.6 for `--experimental-strip-types`. The generator is not on the CI path — the
// committed fixture is — so an unavailable node cannot silently turn the guard green.)
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { recommend } from '../lib/draft-optimizer.ts'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const SRC = path.join(REPO, 'betting_ml/tests/fixtures/nf_c_lda_1_optimizer_parity_input.json')
const OUT = path.join(REPO, 'betting_ml/tests/fixtures/nf_c_lda_1_optimizer_parity.json')

const { board, config, replacement, scenarios } = JSON.parse(fs.readFileSync(SRC, 'utf8'))

const expected = {}
for (const [name, sc] of Object.entries(scenarios)) {
  expected[name] = recommend({
    board,
    config,
    draftedIds: new Set(sc.drafted),
    myPlayerIds: sc.mine,
    // NF-C7 — `undefined` on every pre-NF-C7 scenario, which is the shape a caller that has never
    // heard of depth targets sends, so those scenarios keep pinning the INERT path too.
    depthTargets: sc.depthTargets,
    topN: sc.topN ?? 8,
  }).map((r) => ({
    id: r.player.id,
    pos: r.player.pos,
    score: r.score,
    needLevel: r.needLevel,
    needBonus: r.needBonus,
    seatValue: r.seatValue,
    orderValue: r.orderValue,
    depthShort: r.depthShort,
    depthTier: r.depthTier,
    expectedStarts: r.expectedStarts,
    positionalDropoff: r.positionalDropoff,
    tier: r.tier,
    isLastInTier: r.isLastInTier,
    byeConflict: r.byeConflict,
    mustFill: r.mustFill,
    deferred: r.deferred,
    rationale: r.rationale,
  }))
}

fs.writeFileSync(
  OUT,
  JSON.stringify(
    {
      _generated_by: 'frontend/scripts/gen-optimizer-parity-fixture.mjs',
      _authority: 'frontend/lib/draft-optimizer.ts',
      _input: 'betting_ml/tests/fixtures/nf_c_lda_1_optimizer_parity_input.json',
      replacement,
      expected,
    },
    null,
    1,
  ) + '\n',
)
const n = Object.values(expected).reduce((a, v) => a + v.length, 0)
console.log(`wrote ${OUT}: ${Object.keys(expected).length} scenarios, ${n} recommendations`)
