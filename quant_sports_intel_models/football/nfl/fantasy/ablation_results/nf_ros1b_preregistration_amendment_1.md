# NF-ROS1b — pre-registration amendment 1 (PM rulings 2026-09-17, committed BEFORE any fitting)

Amends `nf_ros1b_preregistration.md` (commit `5f5467a0`). This amendment is written after the PM
reviewed that registration and **before any interval, hurdle probability, ratio, arm score or
name-join result has been computed.** The PM approved D1, D2, D3, D4, D6, D7 and D9 as registered.
The items below record the only rulings that add to, or change, the registered text. No gate,
threshold, population, fold, metric, arm or family parameter moves.

1. **§8 name-join criterion: split by outcome (PM D5).**

   * **`WRONG > 0` ⇒ STOP-AND-REPORT, with no pre-agreed path.** A wrong match credits another
     player's production and also impeaches the join everywhere else. This is unchanged from
     §8 and is now absolute.
   * **`WRONG = 0` and `MISSED > 0` ⇒ node 4 proceeds.** Each MISSED player is served as a stated
     absence under a **fourth absence type, `join_unresolved`**. The PM authorised this type in
     advance, on the record.
     * It must render distinguishably from `not_certified`, `position_not_evaluated` and
       `no_preseason_prior`: its own literal in the contract, and its own count in the manifest.
     * The missed players are named in the closeout.
   * §9's "three distinguishable absences" therefore reads **four** whenever MISSED > 0. The contract
     declares all four literals from birth either way.
   * The test still runs, and is still recorded, whatever the modeling verdict.

2. **§5 reference arm: labelling (PM D3).** `winner@location_shift` is emitted under the key
   `reference_only_winner_at_location_shift`, and every rendered table labels it **"reference only —
   not a trial, not in V, gates nothing."** It never appears in the arm table, the PBO field, or the
   DSR trial list.

3. **Ledger note (PM D2).** The status-at-week-k exclusion stands on the leakage argument in §3.1.
   A status successor will be carded by the PM, not by this session. Its as-of substrate is the
   `nfl_pit_injuries` forward capture, which is accruing now, so its unlock is calendar time, not
   new machinery. That fact goes to `closeout.followUps`.

4. **Environment landmine (PM D8).** The bare-`TOKEN` finding in §11 becomes a one-line CLAUDE.md
   landmine in this story. The durable `s3io.storage_options` fix is platform work carded by the PM
   and is **not** built here.
