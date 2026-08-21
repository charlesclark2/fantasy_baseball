/**
 * NF-C0-Yahoo-ENABLE (Half A) — how long a copied platform roster lives on our side.
 *
 * ⚠️ THIS IS A SECOND SPELLING OF A NUMBER THE SERVER ENFORCES, and it exists only because three
 * user-facing surfaces have to STATE the window (My Teams' deletion notice, the import screen, the
 * privacy policy) and none of them is served it. The authority is
 * `app/backend/services/dynamo.py::PLATFORM_ROSTER_RETENTION_DAYS` — that is the number that
 * actually expires data; this one only describes it.
 *
 * 🔒 The two are pinned equal by `betting_ml/tests/test_nf_c0_yahoo_halfa_compliance.py`. A policy
 * page that promises 30 days over a store that keeps 90 is a compliance statement that is simply
 * untrue, and nothing about the rendered page would look wrong — which is why the agreement is a
 * test rather than a comment asking the next author to remember (E9.61).
 */
export const PLATFORM_ROSTER_RETENTION_DAYS = 30
