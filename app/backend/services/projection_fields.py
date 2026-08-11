"""NF-EPIC 1 — the PUBLIC/PAID split of the NFL projections payload.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHY THIS EXISTS (PM decision, 2026-08-10 — Option C)
═══════════════════════════════════════════════════════════════════════════════════════════════════

The NF-EPIC 1 audit found three values the product sells as PAID sitting in the ANONYMOUS
`/fantasy/nfl/projections` payload, gated only by which component declined to draw them:

    fpStd · fpHalf · the complete raw stat line

A `curl` recovered all three. The PM's ruling: **the raw stat line is PAID** — it is the
re-scorable projection substrate ("the crown jewel"), not the shop-window summary. Anyone who wants
the underlying data gets it through a deliberate, user-facing data API, never by curling a free
endpoint.

⭐ AND THE TWO SCORINGS CANNOT BE WITHHELD ON THEIR OWN. They are ARITHMETIC on the stat line:

    half = fpPpr − 0.5 × rec          standard = fpPpr − 1.0 × rec

measured live to a tenth (Ja'Marr Chase: 261.4 / 213.5 / 165.6 with rec 95.7). So redacting
`fpStd`/`fpHalf` while shipping `rec` is a paywall the reader does in their head. The stat line is
the load-bearing half of this split; the two totals ride along with it.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ ONE SOURCE OF TRUTH, AND IT IS THE SCORER'S OWN MAP — NOT A HAND-WRITTEN DENYLIST
───────────────────────────────────────────────────────────────────────────────────────────────────

`PAID_PLAYER_FIELDS` is DERIVED from `STAT_FIELD` (every payload field the scorer can multiply by a
league weight) rather than listed by hand. That direction is the whole safety property:

  • A hand-written list is a DENYLIST. The next field the exporter adds — a new NF-D projection, a
    new graduated term (NF-C0e added four) — would be PUBLIC BY DEFAULT and leak on the next
    publish, with no code change, no error and no failing test. That is precisely the class
    `entitlement.py` documents as the reason its retired allowlist ran the other way.
  • Deriving it from `STAT_FIELD` means a new SCORABLE stat is paid the moment someone teaches the
    scorer about it, because teaching the scorer IS the act that makes it re-scorable substrate.

⚠️ So the rule for a future field is mechanical: **if it goes in `STAT_FIELD`, it is paid.** If it
is a display value with no scoring weight behind it (`g`, `adp`, `contrib`), it stays public.

───────────────────────────────────────────────────────────────────────────────────────────────────
WHAT STAYS PUBLIC, AND WHY EACH ONE
───────────────────────────────────────────────────────────────────────────────────────────────────

  fpPpr, fpP10, fpP90, fpSd   the free wedge — our number and its 80% band. `fpPpr` is the ONE
                              scoring the free tier shows, and the band is what makes it honest.
  contrib                     ⭐ PM ruling (Q3, 2026-08-10): FREE. Feature attribution is
                              show-our-work transparency and on-brand for honest analytics. It is
                              an EXPLANATION of the free number, not a second number.
  g                           games played — a display divisor for the full-season rate, carries no
                              scoring weight, and is not in `STAT_FIELD`.
  identity / adp              public facts about the player and a third-party market number.

⚠️ `fpPpr` STAYS PUBLIC AND THAT IS DELIBERATE even though `rec` is now withheld: the derivation
runs the other way. Knowing `fpPpr` alone does not yield `fpHalf` without `rec`, which is exactly
what this module removes.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE PUBLIC PAYLOAD IS THE SAME BYTES FOR EVERY CALLER — INCLUDING SUBSCRIBERS
───────────────────────────────────────────────────────────────────────────────────────────────────

`public_projections_payload` takes NO caller argument, and the public route takes no `Request`. A
subscriber gets the identical reduced blob and fetches the paid half separately from
`/fantasy/nfl/projections/full`.

That is not a simplification — it is what preserves G100-D1's CDN cost guardrails. The edge caches
one copy for everybody precisely because the bytes do not vary; a caller-dependent public blob would
re-introduce `cache_control_for`'s "same URL, two bodies" hazard and put every anonymous view back
on the Lambda. A handler that cannot see the caller cannot branch on them.
"""

from __future__ import annotations

# ── stat key → the projections-payload field that backs it ───────────────────────────────────────
#
# ⚠️ MIRROR OF `frontend/lib/league-config.ts::STAT_FIELD` and of
# `NFL_PROFILE.stat_columns` (which names the model's snake_case source columns for the same keys).
# All three move together; `test_nf_epic1_payload_split.py::test_the_stat_field_map_mirrors_the_frontend`
# reads the TS file and compares, so a one-sided edit goes red rather than silently un-gating a
# column or breaking a league's scoring.
STAT_FIELD: dict[str, str] = {
    "pass_att": "passAtt", "pass_cmp": "passCmp", "pass_yds": "passYds", "pass_td": "passTd",
    "pass_int": "passInt",
    "rush_att": "rushAtt", "rush_yds": "rushYds", "rush_td": "rushTd",
    "targets": "tgt", "rec": "rec", "rec_yds": "recYds", "rec_td": "recTd",
    "fumbles_lost": "fum", "two_pt": "twoPt",
    "fg_att": "fgAtt", "fg_made": "fgMade",
    "fg_made_0_39": "fg039", "fg_made_40_49": "fg4049", "fg_made_50_plus": "fg50",
    "fg_missed": "fgMiss",
    "pat_att": "patAtt", "pat_made": "patMade",
    "def_sacks": "sacks", "def_int": "defInt", "def_fumble_rec": "fumRec", "def_td": "defTd",
    "st_td": "stTd", "def_safety": "safety", "def_blocked_kick": "blocked",
    "dst_points_allowed": "paTot",
    "dst_pa_g_0": "paG0", "dst_pa_g_1_6": "paG1_6", "dst_pa_g_7_13": "paG7_13",
    "dst_pa_g_14_17": "paG14_17", "dst_pa_g_18_20": "paG18_20", "dst_pa_g_21_27": "paG21_27",
    "dst_pa_g_28_34": "paG28_34", "dst_pa_g_35_45": "paG35_45", "dst_pa_g_46p": "paG46p",
    # NF-C0e graduated terms. A term that FAILED its held-out degenerate-baseline gate
    # (pat_missed, fum, st_player_td, fumble_rec_td) is deliberately absent here.
    "pass_td_40p": "passTd40p", "rush_td_40p": "rushTd40p", "rec_td_40p": "recTd40p",
    "def_forced_fumble": "ff",
    "dst_yards_allowed": "yaTot",
    "dst_ya_g_0_99": "yaG0_99", "dst_ya_g_100_199": "yaG100_199", "dst_ya_g_200_299": "yaG200_299",
    "dst_ya_g_300_349": "yaG300_349", "dst_ya_g_350_399": "yaG350_399",
    "dst_ya_g_400_449": "yaG400_449", "dst_ya_g_450_499": "yaG450_499",
    "dst_ya_g_500_549": "yaG500_549", "dst_ya_g_550p": "yaG550p",
}

#: The two reference scorings the player page padlocks. Paid because they are derivable from the
#: stat line (see the header) — they cannot be defended separately, and must not be shipped
#: separately either.
PAID_SCORING_FIELDS: frozenset[str] = frozenset({"fpStd", "fpHalf"})

#: ⭐ THE PAID SET, DERIVED. Every scorable stat field, plus the two derived totals.
PAID_PLAYER_FIELDS: frozenset[str] = frozenset(STAT_FIELD.values()) | PAID_SCORING_FIELDS


def public_player_row(row: dict) -> dict:
    """One projection row reduced to what a non-paying caller may hold.

    A plain key drop rather than an allowlist rebuild, because the PAID set is itself derived from
    the scorer's map (header) — so "everything not scorable" stays public automatically and a new
    DISPLAY field does not need registering anywhere to reach the free board.
    """
    return {k: v for k, v in row.items() if k not in PAID_PLAYER_FIELDS}


def public_projections_payload(data: dict) -> dict:
    """The projections payload with every paid field removed from every player row.

    ⚠️ Takes no caller. See the header: the public blob is the same bytes for everybody, which is
    what keeps it edge-cacheable under G100-D1.

    Non-dict rows are passed through untouched rather than dropped — a malformed row must cost only
    itself, never blank the collection (E9.49).
    """
    players = data.get("players")
    if not isinstance(players, list):
        return dict(data)
    return {
        **data,
        "players": [public_player_row(r) if isinstance(r, dict) else r for r in players],
    }


def paid_fields_present(data: dict) -> set[str]:
    """Which PAID fields a payload still carries — the audit instrument.

    Used by the guard tests and by the live verification script to answer the one question the epic
    closes on: *is any paid value recoverable from this payload?* Returns the field names rather
    than a bool so a failure names exactly what leaked.
    """
    out: set[str] = set()
    for row in data.get("players") or []:
        if isinstance(row, dict):
            out.update(k for k in row if k in PAID_PLAYER_FIELDS)
    return out
