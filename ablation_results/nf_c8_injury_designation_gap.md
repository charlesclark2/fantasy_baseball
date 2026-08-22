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
expected absence is not a status at all. Tyson will only move once Arizona actually places him on
one of those lists.

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

## An NF-C8 copy consequence, already fixed

The flag's freshness line originally read *"Injury and roster status as of {date}"*. That is true of
the FEED VINTAGE and invites the reading *"we know about every injury reported by that date and have
priced it in"* — precisely false in the Tyson case. Wording corrected in the same change to name what
actually drives the number. Flagged here because the finding is what exposed it.

## Scope note

Whatever is decided, note that the projection's availability discount and the **flag** are separate
things: NF-C8 renders `g` honestly whatever produces it. A better availability model changes which
rows flag; it does not change the flag.
