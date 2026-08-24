# NF-C8 finding → PM: the availability model sees ROSTER TRANSACTIONS, not injury NEWS

**Status:** open question for the PM. Surfaced by NF-C8 (the availability flag), **not caused by it**.
Nothing here is an NF-C8 defect and nothing here blocks that story.

---

## What was observed

On the served 2026 board, **Jordyn Tyson (WR, rank 27) carries `expected_games = 13.6`** — a normal,
essentially undiscounted projection — while reporting from ~2026-08-18 had him expected to miss
around two months.

The natural first suspicion is staleness. It is not staleness: the board's own injury-input stamp
(`freshness.input_vintage.sleeper_status_as_of`, which NF-C8 now renders under the flag) read
**2026-08-21**, one day old at the time of the check.

## Why the projection does not move — traced, not inferred

The availability discount has exactly one entry point, and it is narrow by construction:

- `season_projection.injury_availability_games` applies a games CAP only when a player's
  `proj_status` is in **`_INJURY_STATUS_GAMES_CAP = {"RES": 4.0, "PUP": 4.0, "NFI": 4.0, "SUS": 7.0}`**
  (`season_projection.py:148`). Everyone else is returned unchanged.
- `proj_status` is produced by `sleeper_injuries_source.map_injury_status`, whose docstring is
  explicit: Sleeper's free-text `injury_status` maps to RES/PUP/NFI/SUS, and returns
  **`None` — i.e. NO OVERRIDE — for a weekly game-report tag** (`sleeper_injuries_source.py:85`).

So the model reacts to a **roster transaction** (IR / PUP / NFI / suspension) and to nothing else.
**Questionable, Doubtful and Out apply a discount of exactly zero**, and a press report of an
expected absence is not a status at all. Tyson will only move once New Orleans actually places him on
one of those lists.

> **📌 Factual correction (2026-08-23, NF-INJ-NEWS-1).** This sentence originally read *"once
> **Arizona** actually places him"*. Jordyn Tyson is a **New Orleans** WR — confirmed against
> the live Sleeper `v1/players/nfl` snapshot (`team = NO`) and against the beat reporting of
> his August absence. Nothing in this document's argument depends on the team, but a false
> premise in a doc is what the next reader builds on, so it is corrected here rather than
> left to be inherited.

This is a **scope limit, working as designed** — the design is leakage-safe and transaction-driven,
which is defensible. It is also, on the evidence of one live check, **not what a reader assumes we
are doing**.

## The operator's ask, recorded

> "we need to be ingesting some sort of injury news sources, whether that's via NLP or not, so we can
> start flagging guys that don't have the formal tag. But if he's listed as Questionable, Doubtful or
> Out, that needs to apply some form of a discount — but we still need to know how long he'd be
> projected to be out."

That last clause is the hard part and it is the reason this is a PM question rather than a ticket:
**a weekly designation carries no duration.** "Out" means out for ONE game; the two-month absence that
prompted this is a news fact, not a status fact. A discount applied per-designation without a
duration model would be a guess wearing a projection's clothing.

## Three things worth settling before anyone builds

1. **Weekly designations are a SEASON-projection input only via a duration model.** `proj_games` is a
   full-season expectation. Mapping "Out" → some fixed games penalty is exactly the kind of
   hand-picked constant this program refuses elsewhere; the honest version is an empirical
   designation → games-missed distribution, fit on history, which is a §0.5 modelling story with a
   real bake-off and not a config change.
2. **A news/NLP feed is a NEW DATA SOURCE with a leakage question attached.** The existing
   availability inputs are pre-season roster facts (`injury_availability_games` documents itself as
   "leakage-safe (a preseason flag)"). A news feed is continuous and its as-of handling would have to
   be right, or a backtest quietly reads the future.
3. **⭐ There is a cheap, honest interim that ships nothing predictive.** We already hold the weekly
   designation — we simply do not act on it. It could be **DISCLOSED without being modelled**: show
   the current designation beside the flag ("listed Out, 2026-08-21") and say plainly that our games
   projection does not yet price it. That converts a silent gap into a visible one at zero modelling
   risk, and it is the same discipline NF-C8 itself follows. ⛔ It must not be dressed up as a
   projection adjustment, because it would not be one.

## An NF-C8 copy consequence — RECOMMENDED here; carded as NF-C10; SHIPPED 2026-08-23 in NF-DTB-1

⚠️ **CORRECTION (NF-DTB-1, 2026-08-23).** This section previously read *"already fixed"* and said the
wording had been *"corrected in the same change"*. **It had not been.** The line shipped and stayed
live reading *"Injury and roster status as of {date}"*, and this write-up asserted a fix that never
landed — the "documented ≠ actually served" class, in a record rather than in code. What the section
actually contained was a RECOMMENDATION; it was carded as **NF-C10** and ruled by the PM (Option 1)
on 2026-08-23, and NF-DTB-1 Half B is what shipped it. The claim is corrected here rather than
deleted, because a record that quietly repairs itself teaches nothing.

The flag's freshness line read *"Injury and roster status as of {date}"*. That is true of the FEED
VINTAGE and invites the reading *"we know about every injury reported by that date and have priced it
in"* — precisely false in the Tyson case. It got worse once NF-C9 shipped: the line renders
**directly beneath** the disclosure saying we hold a player's weekly designation and our
projected-games figure does **not** take it into account, so the two sentences contradicted each
other inside one tooltip, on both surfaces they share.

Ruled wording (Option 1, provenance only): **"Injury/roster feed as of {date}"** — dropping *status*,
which is the word that implies we know the player's standing *and* acted on it. A vintage stamp
describes a FEED, never a player. Pinned on RENDERED output on every surface it appears (board,
projections, player page, and the NF-C9 disclosure) rather than on the constant alone — NF-INJ1-C's
lesson that a constant whose only guard reads the constant is unpinned and looks pinned.

## Scope note

Whatever is decided, note that the projection's availability discount and the **flag** are separate
things: NF-C8 renders `g` honestly whatever produces it. A better availability model changes which
rows flag; it does not change the flag.
