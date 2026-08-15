"""NF-LEAK1 — make paid per-stat reconstruction impractical through the free league's own scorer.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ THE HONEST FRAMING, UP FRONT — THIS IS NOT AND CANNOT BE "ZERO LEAK"
═══════════════════════════════════════════════════════════════════════════════════════════════════

NF-EPIC 1 moved league scoring to the server so the paid stat line never reaches a free browser.
That closed the BULK leak (a `curl` no longer returns the substrate) and left a narrow one, recorded
honestly in that audit's §9: **a server that scores an arbitrary user-supplied scoring config against
the board leaks information about the underlying stat line BY CONSTRUCTION.** Set every weight to
zero but one and the returned `pts` column IS that stat, for all 858 players.

There is no version of "score the user's league on the server" that does not have this property. So
the deliverable is **cost**, not closure: raise the attacker's price past any viable extraction path
and keep every probe attributable to a Cognito `sub`. ⛔ Nothing in this module, and nothing in the
copy around it, may claim the leak is closed.

───────────────────────────────────────────────────────────────────────────────────────────────────
MEASURED BASELINE (`scripts/nf_leak1_reconstruction_cost.py`, real scorer + the real 858-row artifact)
───────────────────────────────────────────────────────────────────────────────────────────────────

    A · isolation      38 writes + 38 reads   38s   100.00% of cells recovered EXACTLY
    B · differencing   39 writes + 39 reads   39s   (survives any "plausible leagues only" rule)
    C · packing        22 writes + 22 reads   22s    99.80% exact  ← the cheapest path

§9 estimated "~50 authenticated round trips" and read that as slow. It is 22 seconds. The estimate
was never the problem; treating it as a bound was.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ WHY THE METER IS ON THE **WRITE**, NOT THE BOARD READ
───────────────────────────────────────────────────────────────────────────────────────────────────

Re-reading a board without changing the config returns the SAME numbers — zero new information. The
channel is opened by the CONFIG CHANGE, so that is the meter. Metering reads instead would throttle
exactly what legitimate users do (open the page, refresh, come back tomorrow) while barely inhibiting
an attacker who needs one read per write.

And only a change to the SCORING counts. Renaming a league, editing the roster, linking a team,
re-importing to refresh a roster snapshot — none of them move the `pts` column, so none of them are
charged. `scoring_fingerprint` is what makes that distinction mechanical rather than remembered.

───────────────────────────────────────────────────────────────────────────────────────────────────
THE THREE LEVERS, AND WHAT EACH IS AND IS NOT WORTH
───────────────────────────────────────────────────────────────────────────────────────────────────

1. **BUDGET** (`charge`) — a durable per-ACCOUNT token bucket on scoring changes. THE PRIMARY LEVER;
   it is the only one that bounds the attack rather than shaping it. Per-account and DURABLE, not the
   per-IP in-memory bucket in `cost_guardrails`: that one is per-Lambda-container (its own docstring
   says so), so it cannot count 39 changes spread over days, and it is keyed on an address the
   attacker can change rather than on the identity they had to create.

2. **SHAPE** (`shape_violations`) — two write-time rules on the config itself:
     • a **weight DYNAMIC RANGE** cap, which is what kills model C. Packing needs ~5 decades of
       weight spread per extra stat; real leagues measure 150–300 (`≈2.5 decades TOTAL`). Capping the
       ratio at 10⁴ leaves 33× headroom over the widest real league and drops packing to 1.0
       stats/config — i.e. it converts the cheapest attack into the most expensive one.
     • a **non-degeneracy** floor, which blocks model A outright — a one-term config is not a fantasy
       league.
   ⚠️ **THE SHAPE RULES DO NOT CLOSE THE LEAK AND MUST NOT BE SOLD AS IF THEY DO.** Model B defeats
   both: a realistic baseline plus δ on one stat is a perfectly plausible league, and differencing
   two admissible configs isolates a stat just as cleanly. Their honest value is that they delete the
   two CHEAP paths and force the attacker onto the one the budget prices correctly.

3. **PROBE DETECTION** (`is_probe_shaped`) — a single-stat delta, once the account has already walked
   `PROBE_TOUCH_THRESHOLD` distinct stats, is charged DOUBLE and logged against the `sub`. A probe
   walk necessarily touches every stat, so it pays the surcharge for most of its length; a real user
   who tweaks PPR, then TE premium, then a fumble weight has touched three and never pays it.
   ⚠️ It is EVADABLE (change two weights per step and the delta test misses), which is why the cost
   claim below is stated on the BUDGET ALONE and the detector is reported as an additional multiplier
   rather than folded into the headline.

───────────────────────────────────────────────────────────────────────────────────────────────────
THE SEPARATION — what a real user gets vs what the attack costs
───────────────────────────────────────────────────────────────────────────────────────────────────

A free account holds ONE league (`FREE_PERSONALIZED_LEAGUE_QUOTA`). The bucket starts FULL at 12
scoring changes and refills 1.5/day:

    legitimate   import a league, then tweak the scoring a handful of times   →  ≤ 12, never blocked
                 come back next week and tweak some more                      →  refilled
    attack       ≥ 38 scoring changes (shape rules forbid fewer)              →  (38 − 12)/1.5 ≈ 17 days
                 with the surcharge, if they do not evade it                  →  ≈ 40 days

Pre-registered gate: **≥ 14 days of sustained probing from one account.** The floor above clears it
without relying on the detector.

⚠️ **THE RESIDUAL, STATED PLAINLY.** Account creation is free, instant and self-serve (NF-EPIC 1 §8),
so an attacker who mints 38 accounts pays 38 signups instead of 17 days. That is bounded by the
per-IP limiter and the email-OTP signup path, and every account is attributable — but it is NOT
closed, and this module does not pretend otherwise. It is the reason the standard here is
"impractical and attributable", not "impossible".

───────────────────────────────────────────────────────────────────────────────────────────────────
WHO IS EXEMPT, AND WHY THAT IS NOT A HOLE
───────────────────────────────────────────────────────────────────────────────────────────────────

A caller with fantasy entitlement is not budgeted. They can already `GET /fantasy/nfl/projections/
full` and receive the entire stat line in one request — metering their league edits protects nothing
and would degrade the product they paid for. The SHAPE rules stay uniform for everyone: they are
league-plausibility rules, no real config violates them, and a rule that applied only to free
accounts would make a subscriber's saved league unsavable the day they lapse.
"""

from __future__ import annotations

import logging
import math

from app.backend.services.projection_fields import STAT_FIELD

logger = logging.getLogger(__name__)

# ── Tunables. Every one is DERIVED FROM A MEASUREMENT, and the measurement is named. ─────────────

#: Weights at or below this are "not scored" — `score_row` skips a zero term entirely.
_EPS = 1e-12

#: The scoring every real football league has. A league that does not pay for passing, rushing and
#: receiving production is not a league; it is a probe wearing a league's schema.
#:
#: MEASURED: all 12 real configs available to check — the 8 shipped presets and the 4 captured
#: imported leagues (two ESPN, one Yahoo) — score ALL SIX.
CORE_STATS: tuple[str, ...] = (
    "pass_yds", "pass_td", "rush_yds", "rush_td", "rec_yds", "rec_td",
)

#: Plain-English names for the six, for the refusal a HUMAN reads.
#:
#: ⚠️ WHY THIS EXISTS AT ALL. `shape_violations` returns strings that go straight into a 400 `detail`
#: and land in a toast under someone's league form. The first version listed the raw column keys
#: (`pass_yds, pass_td, rush_yds, …`), which are our internal spelling of the stat and appear nowhere
#: in the UI a user just filled in — so the message named the fix in a vocabulary the reader has no
#: way to map back to the fields they typed. Naming the stat in the words the form uses is the whole
#: difference between "here is what to change" and "the form is broken".
#:
#: ⛔ NOT a second source of truth for WHICH stats are core — `shape_violations` still iterates
#: `CORE_STATS`, and this map is only consulted for display, with the raw key as the fallback. A key
#: added to `CORE_STATS` without a label here degrades to the key rather than disappearing from the
#: message. Pinned by `test_nf_leak1_scoring_probe_guard.py`.
CORE_STAT_LABELS: dict[str, str] = {
    "pass_yds": "passing yards",
    "pass_td": "passing touchdowns",
    "rush_yds": "rushing yards",
    "rush_td": "rushing touchdowns",
    "rec_yds": "receiving yards",
    "rec_td": "receiving touchdowns",
}


def core_stat_names() -> list[str]:
    """`CORE_STATS` in the words the league form uses. Falls back to the raw key, never drops one."""
    return [CORE_STAT_LABELS.get(stat, stat) for stat in CORE_STATS]

#: How many of `CORE_STATS` a config must actually pay for.
#:
#: ⚠️ A CORE-FAMILY RULE, NOT A TERM COUNT, AND THE DIFFERENCE IS A BYPASS. The first cut of this
#: demanded "at least 4 non-zero scorable terms", which a probe satisfies for free: 15 of the 53
#: keys in `STAT_FIELD` have no column in the published artifact, so three of them pad a
#: one-real-term config to four while contributing exactly 0.0 to `pts`. Requiring CORE families
#: cannot be padded that way, because their columns are the ones that always carry data.
#:
#: ⭐⭐ AND IT IS 2 BECAUSE 2 IS WHAT THE MEASUREMENT SUPPORTS — NOT BECAUSE 2 FELT SAFE. This shipped
#: as 4 first, on the reasoning that forcing more big-range stats into the config would eat the
#: window a packed place needs. `admissible_attack_plan` says otherwise: at 1, 2, 3, 4 and 6 the
#: surviving attack is IDENTICAL (32 changes, 1.23 stats/change, 92.22% exact), because the attacker
#: DIFFERENCES against their own baseline and the core terms cancel exactly. So every threshold above
#: 2 was pure false-refusal risk for zero measured protection.
#:
#: 2 is the smallest value with a property worth having: no SINGLE-term config is admissible, at any
#: stat. (1 is not enough — a probe isolating a core stat satisfies it.) That is the whole job of
#: this rule; it blocks model A and hands the attacker model B, which the budget prices.
MIN_CORE_STATS = 2

#: The widest ratio between the largest and smallest non-zero weight in ONE config.
#:
#: MEASURED: the 8 presets sit at 150 and the widest real imported league at 300, so 400 clears every
#: real config with room while cutting the attacker's packing depth to 1.27 stats/config (from 2.11
#: at 10⁴ and 1.73 at the status-quo-implied 10³).
#:
#: 🪤 THE FIRST VALUE SHIPPED HERE WAS 10⁴ AND IT MADE THE ATTACK CHEAPER, which the before/after
#: harness caught and no amount of reading would have. The pre-existing `|w| ≤ 1000` bound in
#: `LeagueSave` already implied a ratio ceiling of ~10³ for any config whose smallest weight is ~1,
#: so a "new" cap of 10⁴ was a LOOSENING wearing a guardrail's clothes. A range rule is only a
#: guardrail below the range the system already enforced — measure it against the status quo, never
#: against zero.
MAX_WEIGHT_RATIO = 400.0

#: Token bucket on SCORING CHANGES, per account. Capacity first, then the sustained rate.
#:
#: 12 is a deliberately generous setup session — "a handful of tweaks" is ~5, and a free account has
#: exactly ONE league to spend them on. 1/day (7/week) is far above any real editing cadence.
#:
#: ⭐ TUNED AGAINST THE ATTACKER'S MEASURED BEST SURVIVING PLAN, NOT THE NAIVE ONE. With the shape
#: rules in force, `admissible_attack_plan` covers all 38 stats in 32 changes (1.23 stats/change —
#: the small-range DST/kicker tail still packs 2–3 at a time inside the admissible weight window;
#: `pass_yds` and friends cannot). (32 − 12)/1.0 ≈ 20 days, against a pre-registered gate of 14.
#: Tuning against the 39-change one-stat-per-change figure instead would have set a rate the attacker
#: beats by a third, and nothing would have said so.
BUDGET_BURST = 12.0
BUDGET_REFILL_PER_DAY = 1.0

#: What a probe-shaped change costs instead of 1.
PROBE_SURCHARGE = 2.0

#: How many DISTINCT stats an account must have walked ONE AT A TIME before a further single-stat
#: delta is treated as probe-shaped. Below this it is indistinguishable from a real user tuning their
#: league one knob at a time, which is the normal way anybody edits scoring.
#:
#: 🪤 THE COUNTER IS FED ONLY BY SINGLE-STAT DELTAS, AND THE FIRST CUT WAS NOT — which armed the
#: detector on every real account instantly. A league's FIRST save is a delta from nothing, so it
#: "touches" all ~28 of its terms at once; counting those made every subsequent one-knob tweak by a
#: real user probe-shaped from their second save onward. A bulk write (an import, switching preset)
#: is not a step in a walk, and must not be counted as one.
#:
#: 10 distinct one-at-a-time stats is already an unusual amount of tuning for one league; a
#: reconstruction walk must touch all 38, so it still pays the surcharge for ~28 of its steps.
PROBE_TOUCH_THRESHOLD = 10

#: Bound on the stored `touched` list, so the ledger cannot grow without limit on the user item.
_MAX_TOUCHED = 128

SECONDS_PER_DAY = 86400.0


# ── The scoring fingerprint ───────────────────────────────────────────────────────────────────────


def scoring_fingerprint(config: dict | None) -> dict[str, float]:
    """The SCORABLE weights a config expresses, flattened — `{term_key: weight}`.

    Position bonuses are folded in under a `pos:stat` key rather than dropped: `score_row` adds them
    to `pts` exactly like a per-stat weight, so they are a second channel into the same leak. A rule
    that policed `per_stat` alone would leave the whole attack available through
    `position_bonuses` — the "enumerate every surface, not the obvious one" class.

    Non-scorable keys (a platform term the scorer captures but never applies) are EXCLUDED: they
    cannot move `pts`, so charging for them would bill a user for fidelity we asked them to keep.
    """
    scoring = (config or {}).get("scoring") or {}
    out: dict[str, float] = {}

    for key, raw in (scoring.get("per_stat") or {}).items():
        if key in STAT_FIELD:
            out[str(key)] = _as_float(raw)

    for pos, terms in (scoring.get("position_bonuses") or {}).items():
        if not isinstance(terms, dict):
            continue
        for key, raw in terms.items():
            if key in STAT_FIELD:
                out[f"{pos}:{key}"] = _as_float(raw)

    return {k: v for k, v in out.items() if abs(v) > _EPS}


def scoring_changed(before: dict | None, after: dict | None) -> bool:
    """Whether the SCORING moved between two configs — the only edit this module charges for."""
    return scoring_fingerprint(before) != scoring_fingerprint(after)


def _as_float(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


# ── Lever 2 — write-time shape rules ──────────────────────────────────────────────────────────────


def shape_violations(config: dict | None) -> list[str]:
    """Human-readable reasons this config may not be saved. Empty ⇒ acceptable.

    Returns MESSAGES rather than a bool so the refusal a user sees names what to change — a paywall
    that says only "no" on a config someone typed reads as a broken form.
    """
    fingerprint = scoring_fingerprint(config)
    problems: list[str] = []

    # Counted on the bare stat key, so a weight parked in `position_bonuses` satisfies it too — a
    # real league expressing TE-premium receiving that way is not degenerate.
    core = sum(
        1 for stat in CORE_STATS
        if any(k == stat or k.endswith(f":{stat}") for k in fingerprint)
    )
    if core < MIN_CORE_STATS:
        names = core_stat_names()
        problems.append(
            "A league needs to award points for at least "
            f"{MIN_CORE_STATS} of the main ways players score — "
            f"{', '.join(names[:-1])} or {names[-1]}. "
            f"This scoring awards points for {core} of them, so we can't save it as a league"
        )

    magnitudes = [abs(w) for w in fingerprint.values()]
    if magnitudes:
        smallest, largest = min(magnitudes), max(magnitudes)
        if smallest > 0 and largest / smallest > MAX_WEIGHT_RATIO:
            # ⚠️ THE WORD "range" IS LOAD-BEARING, not decoration.
            # `test_nf_leak1_scoring_probe_guard.py::test_a_magnitude_packed_probe_is_refused`
            # keys on it to tell WHICH of the two shape rules fired — a refusal that named neither
            # would let a config refused by the core-stat rule pass a test written for this one.
            problems.append(
                f"Your scoring values cover too wide a range: one of them is "
                f"{largest / smallest:,.0f} times another ({smallest:g} against {largest:g}). "
                f"Real leagues stay within about {MAX_WEIGHT_RATIO:g}x. It is usually a value "
                "typed in the wrong units — check your largest and smallest"
            )

    return problems


# ── Lever 3 — probe detection ─────────────────────────────────────────────────────────────────────


def changed_terms(before: dict[str, float], after: dict[str, float]) -> list[str]:
    """Term keys whose weight differs between two fingerprints (an add or a drop counts)."""
    return sorted(
        k for k in set(before) | set(after)
        if abs(before.get(k, 0.0) - after.get(k, 0.0)) > _EPS
    )


def is_probe_shaped(before: dict[str, float], after: dict[str, float], touched: list[str]) -> bool:
    """A single-stat delta from an account that has already walked many distinct stats.

    ⚠️ EVADABLE ON PURPOSE-BUILT INPUT — moving two weights per step (advance one, revert the last)
    isolates a stat just as well and this test misses it. It is a surcharge on the OBVIOUS walk, not
    a gate, and the module's cost claim does not depend on it firing.
    """
    delta = changed_terms(before, after)
    return len(delta) == 1 and len(touched) >= PROBE_TOUCH_THRESHOLD


# ── Lever 1 — the durable per-account budget ──────────────────────────────────────────────────────


def new_ledger(now: float) -> dict:
    """A full bucket. A brand-new account starts with its whole setup session available."""
    return {"tokens": BUDGET_BURST, "checked_at": now, "changes": 0, "probe_hits": 0,
            "last_scoring": {}, "touched": []}


def _coerce(ledger: dict | None, now: float) -> dict:
    """Read a stored ledger defensively — a malformed one must not lock a user out of their league.

    Fails OPEN to a full bucket rather than closed: the failure this protects against is our own
    storage, and the alternative (treating unreadable state as "no budget") would present to a real
    user as their league becoming permanently unsavable, which is a far worse outcome than one
    attacker getting one extra bucket.
    """
    if not isinstance(ledger, dict):
        return new_ledger(now)
    out = new_ledger(now)
    try:
        out["tokens"] = min(BUDGET_BURST, max(0.0, float(ledger.get("tokens", BUDGET_BURST))))
        out["checked_at"] = float(ledger.get("checked_at", now))
        out["changes"] = int(ledger.get("changes", 0) or 0)
        out["probe_hits"] = int(ledger.get("probe_hits", 0) or 0)
        last = ledger.get("last_scoring")
        out["last_scoring"] = (
            {str(k): _as_float(v) for k, v in last.items()} if isinstance(last, dict) else {}
        )
        touched = ledger.get("touched")
        out["touched"] = [str(t) for t in touched][:_MAX_TOUCHED] if isinstance(touched, list) else []
    except (TypeError, ValueError):
        logger.warning("scoring_probe_guard: unreadable ledger; starting a fresh bucket")
        return new_ledger(now)
    return out


class BudgetVerdict:
    """The outcome of charging one scoring change, plus the ledger to persist."""

    __slots__ = ("allowed", "retry_after_seconds", "ledger", "probe_shaped", "cost")

    def __init__(self, allowed: bool, retry_after_seconds: int, ledger: dict,
                 probe_shaped: bool, cost: float) -> None:
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds
        self.ledger = ledger
        self.probe_shaped = probe_shaped
        self.cost = cost


def charge(ledger: dict | None, after_config: dict | None, now: float) -> BudgetVerdict:
    """Charge one scoring change against the account's bucket.

    ⭐ THE BUCKET IS PER-ACCOUNT AND THE STATE IS PERSISTED OFF THE LEAGUE, so `DELETE` then `POST`
    does not reset it. That bypass is the whole reason this cannot ride on the league record: a free
    account may only hold one league, but it may delete and recreate that league without limit, and
    a per-league counter would hand back a full bucket every time.

    ⚠️ A REFUSED CHANGE COSTS NOTHING. The refill clock still advances (so a throttled caller is not
    pinned at zero) but no token is spent, otherwise retrying would push the unlock time further away
    on every attempt — a limiter that punishes retries is one that never lets a real user back in.
    """
    state = _coerce(ledger, now)

    elapsed = max(0.0, now - float(state["checked_at"]))
    tokens = min(
        BUDGET_BURST,
        float(state["tokens"]) + elapsed * (BUDGET_REFILL_PER_DAY / SECONDS_PER_DAY),
    )
    state["checked_at"] = now

    before = dict(state["last_scoring"])
    after = scoring_fingerprint(after_config)
    delta = changed_terms(before, after)
    probe = is_probe_shaped(before, after, state["touched"])
    cost = PROBE_SURCHARGE if probe else 1.0

    if tokens < cost:
        state["tokens"] = tokens
        deficit = cost - tokens
        retry = int(math.ceil(deficit / (BUDGET_REFILL_PER_DAY / SECONDS_PER_DAY)))
        return BudgetVerdict(False, max(1, retry), state, probe, cost)

    state["tokens"] = tokens - cost
    state["changes"] = int(state["changes"]) + 1
    state["last_scoring"] = after
    if probe:
        state["probe_hits"] = int(state["probe_hits"]) + 1

    # ⚠️ ONLY a single-stat delta counts as a step in a walk. A bulk write — the first save of a
    # league, an import, switching preset — moves every term at once and is not a probe step; see
    # `PROBE_TOUCH_THRESHOLD` for the false-positive that counting them produced.
    if len(delta) == 1:
        touched = list(state["touched"])
        if delta[0] not in touched:
            touched.append(delta[0])
        state["touched"] = touched[-_MAX_TOUCHED:]

    return BudgetVerdict(True, 0, state, probe, cost)


def throttle_message(retry_after_seconds: int) -> str:
    """What a throttled caller is told. Names the real constraint and does not accuse anybody."""
    hours = max(1, int(round(retry_after_seconds / 3600.0)))
    return (
        "You've changed this league's scoring a lot in a short time. "
        f"Scoring changes are limited on the free plan — try again in about {hours} "
        f"hour{'s' if hours != 1 else ''}, or subscribe for unlimited edits. "
        "Everything else about your league (name, roster, linked team) can still be edited."
    )
