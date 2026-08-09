"""
build_batter_prop_substrate.py
──────────────────────────────
Assemble the MLB batter-prop PHASE-2 training substrate ONCE → a single Parquet.

Grain: one row per (game_pk, batter_id, market_key).
Markets: batter_hits, batter_home_runs, batter_total_bases.

Each row carries:
  • the REALIZED outcome for that market (from Statcast PA events)
  • the de-vigged CONSENSUS closing line + P(over) (benchmark, NOT a fit target)
  • leak-safe PREGAME features (lagged rolling stats, EB posteriors, park factors)
  • full join PROVENANCE so every resolution decision is auditable

SF-free: reads S3 parquet via DuckDB only.  boto3/DuckDB use the instance-role
credential chain (⛔ never os.environ AWS keys — the AKID landmine).

WHY THIS SCRIPT EXISTS (and what it fixes)
The obvious way to attach a prop line to a game is `mart_game_odds_bridge`
(odds_api_event_id → game_pk).  Measured, that bridge resolves only **66.9%** of
batter-prop events — and just **27.2%** in 2023 — because the bridge is built from
the h2h/totals odds capture and only carries an event_id for games THAT capture
covered.  The prop feed has its own, wider event set.

This script adds a second resolver: the prop's (home_team, away_team,
commence_time) matched against the Stats API spine's scheduled FIRST PITCH, with
both team-name sides folded through `dim_team_name_lookup`.  Combined coverage is
**~97%** (2023: 27.2% → 97.2%).  Where BOTH resolvers fire they agree on
4,636/4,640 events (99.91%), which is what validates the fallback — it is not
trusted on assertion, it is checked against the bridge wherever the bridge exists.

⚠️ `dim_team_name_lookup.team_id` is an INTERNAL 1–31 id space, NOT the MLB Stats
API team ids (117 = Astros) the spine carries.  Both name sides must be folded
THROUGH the lookup; joining lookup.team_id directly to spine.home_team_id silently
returns zero rows.

LEAKAGE CONTRACT (every feature is strictly pre-first-pitch)
  • prop lines      : only snapshots with snapshot_ts < commence_time; the LATEST
                      such snapshot per (event, book, player) = the closing line.
  • rolling stats   : `mart_batter_rolling_stats` windows are
                      RANGE … PRECEDING AND CURRENT ROW — i.e. INCLUSIVE of the
                      labelled game.  They are LAGGED one game per batter here.
                      Using them unlagged leaks the label.
  • EB posteriors   : `eb_batter_posteriors_raw` is already pregame (built from
                      confirmed lineups ~3h out) and is used as-is.
  • park factors    : joined on the PRIOR season (season - 1).

USAGE
    # Smoke (one season, ~1 min) — proves the path end-to-end:
    uv run scripts/build_batter_prop_substrate.py --seasons 2025 --smoke

    # Full build (all seasons; >2 min → operator LAPTOP command):
    uv run scripts/build_batter_prop_substrate.py

    # Inspect the result:
    uv run python -c "import pandas as pd; d=pd.read_parquet('<out>'); print(d.shape); print(d.head())"

OUTPUT (default)
    s3://baseball-betting-ml-artifacts/baseball/research/batter_prop_substrate/
        batter_prop_substrate_v1.parquet
  (or a local path via --out)
"""

from __future__ import annotations

import argparse
import logging
import sys
import unicodedata
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from betting_ml.utils.prop_edge import (  # noqa: E402
    last_initial_key,
    normalize_name,
    ref_display_name,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BUCKET     = "baseball-betting-ml-artifacts"
AWS_REGION = "us-east-2"
LAKEHOUSE  = f"s3://{BUCKET}/baseball/lakehouse"
PROPS      = f"s3://{BUCKET}/mlb/props"
DEFAULT_OUT = (
    f"s3://{BUCKET}/baseball/research/batter_prop_substrate/"
    "batter_prop_substrate_v1.parquet"
)

# market → (realized-outcome column on the batter-game aggregate)
MARKETS = {
    "batter_hits":        "hits",
    "batter_home_runs":   "home_runs",
    "batter_total_bases": "total_bases",
}

ALL_SEASONS = [2023, 2024, 2025, 2026]

# First-pitch match tolerance.  The Odds API commence_time and the Stats API
# scheduled first pitch are the same physical quantity but are not byte-identical
# (books round, schedules shift).  180 min is wide enough to absorb that and still
# far narrower than the ~24h gap to the next game in a series.
FIRST_PITCH_TOLERANCE_MIN = 180


# ── name keys ──────────────────────────────────────────────────────────────────

def _fold_quotes(s: str) -> str:
    """Fold Unicode quote characters to ASCII before normalisation.

    ⚠️ `prop_edge.normalize_name` maps the ASCII apostrophe to a SPACE
    ("Ryan O'Hearn" → 'ryan o hearn') but leaves the Unicode RIGHT SINGLE
    QUOTATION MARK (U+2019) untouched, where it is then dropped
    ("Ryan O’Hearn" → 'ryan ohearn').  The two forms therefore do NOT match each
    other, and The Odds API emits the CURLY form while the player reference table
    uses ASCII — so every apostrophe surname (O'Hearn, O'Neill, D'Arnaud) fails to
    resolve.  Folding here fixes it for this substrate WITHOUT touching the shared
    util, which is on the pitcher-K SERVING path (this is a deploy-held research
    story; changing serving-path name resolution is out of scope).  Reported in the
    handoff as a separate finding.
    """
    if not isinstance(s, str):
        return ""
    return s.replace("\u2019", "'").replace("\u02bc", "'").replace("\u2018", "'")


def _name_key(name: str) -> str:
    """Order-independent normalised key — folds 'Last, First' vs 'First Last'."""
    return " ".join(sorted(normalize_name(_fold_quotes(name)).split()))


def _li_key(name: str) -> str:
    """(last_token, first_initial) fallback key, as a string.

    Catches the legal-vs-common first-name split The Odds API produces:
    'Thomas Edman'→'Tommy Edman', 'Caleb Raleigh'→'Cal Raleigh',
    'Zachary Neto'→'Zach Neto'.  Deliberately ambiguous by construction — the
    ambiguity is resolved downstream by ACTUAL APPEARANCE in that game.
    """
    return str(last_initial_key(normalize_name(_fold_quotes(name))))


# ── connection ─────────────────────────────────────────────────────────────────

def connect(memory_limit_gb: int) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # credential_chain: resolves the instance role on EC2 and the local profile on a
    # laptop.  Never pass explicit keys (the AKID / os.environ landmine).
    con.execute(
        f"CREATE OR REPLACE SECRET s (TYPE S3, PROVIDER credential_chain, "
        f"REGION '{AWS_REGION}')"
    )
    con.execute(f"SET memory_limit='{memory_limit_gb}GB'")
    con.execute("SET preserve_insertion_order=false")
    return con


# ── step 1: realized batter-game outcomes ──────────────────────────────────────

def build_outcomes(con, seasons: list[int]) -> None:
    """Aggregate Statcast PA events → one row per (game_pk, batter_id).

    `mart_pa_outcome_substrate` is the canonical PA-grain model but is
    duckdb-target-only and is NOT materialised to S3, so its event→label mapping is
    reproduced here against `stg_batter_pitches` directly (the same pattern
    train_pa_outcome_v1.py uses).  The mapping is kept byte-aligned with
    dbt/models/mart/mart_pa_outcome_substrate.sql lines 158-181.
    """
    years = ",".join(str(s) for s in seasons)
    globs = ", ".join(
        f"'{LAKEHOUSE}/stg_batter_pitches/year={s}/**/*.parquet'" for s in seasons
    )
    log.info("outcomes: aggregating PA events for %s …", years)
    con.execute(f"""
        CREATE OR REPLACE TABLE outcomes AS
        WITH pa AS (
            SELECT game_pk::BIGINT     AS game_pk,
                   batter_id::BIGINT   AS batter_id,
                   game_date::DATE     AS game_date,
                   plate_appearance_event AS ev
            FROM read_parquet([{globs}], union_by_name=true)
            WHERE plate_appearance_event IS NOT NULL
        )
        SELECT
            game_pk, batter_id, game_date,
            count(*)                                                    AS pa,
            sum(CASE WHEN ev IN ('single','double','triple','home_run')
                     THEN 1 ELSE 0 END)                                 AS hits,
            sum(CASE WHEN ev = 'home_run' THEN 1 ELSE 0 END)            AS home_runs,
            sum(CASE WHEN ev = 'single'   THEN 1
                     WHEN ev = 'double'   THEN 2
                     WHEN ev = 'triple'   THEN 3
                     WHEN ev = 'home_run' THEN 4
                     ELSE 0 END)                                        AS total_bases,
            sum(CASE WHEN ev = 'single' THEN 1 ELSE 0 END)              AS singles,
            sum(CASE WHEN ev = 'double' THEN 1 ELSE 0 END)              AS doubles,
            sum(CASE WHEN ev = 'triple' THEN 1 ELSE 0 END)              AS triples,
            sum(CASE WHEN ev IN ('walk','intent_walk') THEN 1 ELSE 0 END) AS walks,
            sum(CASE WHEN ev IN ('strikeout','strikeout_double_play')
                     THEN 1 ELSE 0 END)                                 AS strikeouts
        FROM pa
        GROUP BY 1, 2, 3
    """)
    n = con.execute("SELECT count(*) FROM outcomes").fetchone()[0]
    log.info("outcomes: %s batter-games", f"{n:,}")


# ── step 2: event_id → game_pk (bridge + first-pitch fallback) ─────────────────

def build_event_map(con, seasons: list[int]) -> pd.DataFrame:
    """Resolve prop event_id → game_pk by two independent methods, and report
    their agreement.  Returns the per-season provenance table."""
    season_list = ",".join(str(s) for s in seasons)
    date_globs = ", ".join(
        f"'{PROPS}/market={m}/season=*/date=*/data.parquet'" for m in MARKETS
    )

    # NOTE: CREATE TABLE, not CREATE VIEW.  The props parquet carries corrupt
    # column statistics that trip DuckDB's perfect-hash aggregate
    # ("aggregate group … exceeded total groups") when grouped through a view.
    # Materialising normalises the stats.
    con.execute(f"""
        CREATE OR REPLACE TABLE prop_events AS
        SELECT DISTINCT
            season::INTEGER          AS season,
            event_id,
            home_team, away_team,
            commence_time::TIMESTAMP AS commence_ts
        FROM read_parquet([{date_globs}], union_by_name=true)
        WHERE season IN ({season_list})
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE team_lookup AS
        SELECT name_lower, team_id
        FROM read_parquet('{LAKEHOUSE}/dim_team_name_lookup/**/*.parquet',
                          union_by_name=true)
    """)

    # Postponed rows are excluded: MLB REUSES the gamePk for the makeup, and a
    # postponed row carries the ORIGINAL (stale) first pitch, which would win the
    # nearest-first-pitch match against the real game.
    con.execute(f"""
        CREATE OR REPLACE TABLE spine AS
        SELECT game_pk::BIGINT        AS game_pk,
               home_team_name, away_team_name,
               game_date::TIMESTAMP   AS first_pitch,
               official_date::DATE    AS official_date,
               venue_id::BIGINT       AS venue_id,
               season::INTEGER        AS season
        FROM read_parquet('{LAKEHOUSE}/stg_statsapi_games/**/*.parquet',
                          union_by_name=true)
        WHERE season IN ({season_list})
          AND coalesce(detailed_state, '') <> 'Postponed'
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE bridge AS
        SELECT DISTINCT odds_api_event_id AS event_id, game_pk::BIGINT AS game_pk
        FROM read_parquet('{LAKEHOUSE}/mart_game_odds_bridge/**/*.parquet',
                          union_by_name=true)
        WHERE odds_api_event_id IS NOT NULL
    """)

    # Fallback: fold BOTH name sides through dim_team_name_lookup into its own
    # internal id space, then match on scheduled first pitch.
    con.execute(f"""
        CREATE OR REPLACE TABLE fp_candidates AS
        SELECT pe.event_id, sp.game_pk,
               abs(date_diff('minute', pe.commence_ts, sp.first_pitch)) AS delta_min
        FROM prop_events pe
        JOIN team_lookup ph
          ON ph.name_lower = lower(regexp_replace(trim(pe.home_team), '^G[12] ', ''))
        JOIN team_lookup pa
          ON pa.name_lower = lower(regexp_replace(trim(pe.away_team), '^G[12] ', ''))
        JOIN spine sp
          ON abs(date_diff('minute', pe.commence_ts, sp.first_pitch))
             <= {FIRST_PITCH_TOLERANCE_MIN}
        JOIN team_lookup sh
          ON sh.name_lower = lower(trim(sp.home_team_name)) AND sh.team_id = ph.team_id
        JOIN team_lookup sa
          ON sa.name_lower = lower(trim(sp.away_team_name)) AND sa.team_id = pa.team_id
    """)

    con.execute("""
        CREATE OR REPLACE TABLE fp_best AS
        SELECT event_id, game_pk FROM (
            SELECT *, row_number() OVER (PARTITION BY event_id
                                         ORDER BY delta_min, game_pk) AS rn
            FROM fp_candidates
        ) WHERE rn = 1
    """)

    con.execute("""
        CREATE OR REPLACE TABLE event_map AS
        SELECT pe.season, pe.event_id,
               coalesce(b.game_pk, f.game_pk) AS game_pk,
               CASE WHEN b.game_pk IS NOT NULL THEN 'bridge'
                    WHEN f.game_pk IS NOT NULL THEN 'first_pitch'
                    ELSE 'unresolved' END     AS resolver,
               (b.game_pk IS NOT NULL AND f.game_pk IS NOT NULL
                AND b.game_pk <> f.game_pk)   AS resolvers_disagree
        FROM prop_events pe
        LEFT JOIN bridge b ON b.event_id = pe.event_id
        LEFT JOIN fp_best f ON f.event_id = pe.event_id
    """)

    prov = con.execute("""
        SELECT season,
               count(*)                                                  AS prop_events,
               sum(CASE WHEN resolver='bridge'      THEN 1 ELSE 0 END)   AS via_bridge,
               sum(CASE WHEN resolver='first_pitch' THEN 1 ELSE 0 END)   AS via_first_pitch,
               sum(CASE WHEN resolver='unresolved'  THEN 1 ELSE 0 END)   AS unresolved,
               round(100.0 * sum(CASE WHEN resolver<>'unresolved' THEN 1 ELSE 0 END)
                     / count(*), 1)                                      AS pct_resolved,
               sum(CASE WHEN resolvers_disagree THEN 1 ELSE 0 END)       AS disagree
        FROM event_map GROUP BY 1 ORDER BY 1
    """).fetchdf()
    log.info("event_id → game_pk provenance:\n%s", prov.to_string(index=False))
    return prov


# ── step 3: player_name → batter_id ────────────────────────────────────────────

def build_name_map(con, seasons: list[int]) -> None:
    """Two-tier name resolution, disambiguated by ACTUAL APPEARANCE.

    Tier 1 exact normalised key; tier 2 (last, first-initial).  Both may map a
    name to several ids; the ambiguity is then resolved by requiring the id to
    have actually batted in THAT game — which is what makes an otherwise unsafe
    fallback safe (a 'Jesus Rodriguez' collision cannot survive it).
    """
    ref = con.execute(f"""
        SELECT mlb_bam_id::BIGINT AS batter_id, first_name, last_name
        FROM read_parquet('{LAKEHOUSE}/stg_ref_players/**/*.parquet',
                          union_by_name=true)
        WHERE mlb_bam_id IS NOT NULL
    """).fetchdf()
    ref["display"]  = [ref_display_name(f, l) for f, l in zip(ref.first_name, ref.last_name)]
    ref["name_key"] = [_name_key(d) for d in ref.display]
    ref["li_key"]   = [_li_key(d)   for d in ref.display]
    con.register("ref_players_df", ref[["batter_id", "name_key", "li_key"]])
    con.execute("CREATE OR REPLACE TABLE ref_players AS SELECT * FROM ref_players_df")

    date_globs = ", ".join(
        f"'{PROPS}/market={m}/season=*/date=*/data.parquet'" for m in MARKETS
    )
    season_list = ",".join(str(s) for s in seasons)
    names = con.execute(f"""
        SELECT DISTINCT player_name
        FROM read_parquet([{date_globs}], union_by_name=true)
        WHERE season IN ({season_list}) AND player_name IS NOT NULL
    """).fetchdf()
    names["name_key"] = [_name_key(n) for n in names.player_name]
    names["li_key"]   = [_li_key(n)   for n in names.player_name]
    con.register("prop_names_df", names)
    con.execute("CREATE OR REPLACE TABLE prop_names AS SELECT * FROM prop_names_df")

    # Candidate ids per prop name: exact key first, then last-initial.  Both tiers
    # are kept as CANDIDATES (not collapsed) so appearance can arbitrate.
    con.execute("""
        CREATE OR REPLACE TABLE name_candidates AS
        SELECT pn.player_name, r.batter_id, 'exact' AS match_tier
        FROM prop_names pn JOIN ref_players r ON r.name_key = pn.name_key
        UNION
        SELECT pn.player_name, r.batter_id, 'last_initial' AS match_tier
        FROM prop_names pn JOIN ref_players r ON r.li_key = pn.li_key
        WHERE pn.name_key NOT IN (SELECT name_key FROM ref_players)
    """)
    stats = con.execute("""
        SELECT (SELECT count(*) FROM prop_names)                                AS names,
               count(DISTINCT player_name)                                      AS with_candidate,
               sum(CASE WHEN match_tier='exact' THEN 1 ELSE 0 END)              AS exact_rows,
               sum(CASE WHEN match_tier='last_initial' THEN 1 ELSE 0 END)       AS li_rows
        FROM name_candidates
    """).fetchdf()
    log.info("name resolution candidates:\n%s", stats.to_string(index=False))


# ── step 4: de-vigged consensus closing line ───────────────────────────────────

def build_lines(con, seasons: list[int]) -> None:
    """Closing consensus line + de-vigged P(over) per (event, player, market).

    De-vig method is the PLAIN UNWEIGHTED one used by `mart_odds_consensus`:
    per book, convert both American prices to implied probability and normalise
    the pair to sum to 1; then average across books, unweighted.

    ⚠️ Only TWO-SIDED quotes can be de-vigged.  Measured two-sided share:
    batter_hits 75.7%, batter_total_bases 81.2%, batter_home_runs **33.2%** — and
    for HR that is a BOOK property, not noise (betmgm/draftkings/pointsbetus/
    unibet_us ~100% two-sided; fanduel/williamhill_us/mybookieag 0%, offering the
    one-way "anytime HR" form).  One-sided quotes are RETAINED with a NULL
    devigged probability and counted, never silently imputed to 50/50.
    """
    season_list = ",".join(str(s) for s in seasons)
    frames = []
    for market in MARKETS:
        con.execute(f"""
            CREATE OR REPLACE TABLE raw_{market} AS
            SELECT event_id, bookmaker_key, player_name,
                   line::DOUBLE        AS line,
                   over_price::DOUBLE  AS over_price,
                   under_price::DOUBLE AS under_price,
                   snapshot_ts, commence_time
            FROM read_parquet('{PROPS}/market={market}/season=*/date=*/data.parquet',
                              union_by_name=true)
            WHERE season IN ({season_list})
              AND line IS NOT NULL
              AND snapshot_ts < commence_time     -- pregame only (leakage gate)
        """)
        # Closing line = the LATEST pregame snapshot per (event, book, player, line).
        con.execute(f"""
            CREATE OR REPLACE TABLE close_{market} AS
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY event_id, bookmaker_key, player_name, line
                    ORDER BY snapshot_ts DESC) AS rn
                FROM raw_{market}
            ) WHERE rn = 1
        """)
        # Per-book two-way de-vig, kept at BOOK level — the consensus is deliberately
        # NOT formed here.
        #
        # ⚠️⚠️ Aggregating to a consensus keyed on `player_name` (the obvious shape, and
        # the one this script originally used) SPLITS ONE PLAYER ACROSS TWO ROWS whenever
        # the feed spells them two ways — "Matt Duffy"/"Matthew Duffy",
        # "MJ Melendez"/"M.J. Melendez" — because both spellings resolve to the SAME
        # batter_id downstream.  Measured on the first published artifact: 11,461
        # duplicate (game_pk, batter_id, market_key) keys, 23,720 rows, ~99.7% of them in
        # 2023, and the pairs carried DIFFERENT lines and probabilities — so the books'
        # quotes for one player were being split into two competing half-consensuses
        # rather than pooled.  (Our own two-tier name matching is a main driver: the
        # `exact` tier catches one spelling and `last_initial` the other.)
        #
        # ⇒ resolve player_name → batter_id FIRST (in `assemble`), then form the consensus
        # over the UNION of books for that batter.  Grouping by a display string is the
        # bug; grouping by the resolved identity is the fix.
        con.execute(f"""
            CREATE OR REPLACE TABLE quotes_{market} AS
            SELECT event_id, player_name,
                   '{market}'  AS market_key,
                   bookmaker_key, line,
                   (over_price IS NOT NULL AND under_price IS NOT NULL) AS two_sided,
                   CASE WHEN over_price IS NOT NULL AND under_price IS NOT NULL THEN
                       (CASE WHEN over_price  < 0 THEN abs(over_price)/(abs(over_price)+100.0)
                             ELSE 100.0/(over_price+100.0) END)
                       / nullif(
                           (CASE WHEN over_price  < 0 THEN abs(over_price)/(abs(over_price)+100.0)
                                 ELSE 100.0/(over_price+100.0) END)
                         + (CASE WHEN under_price < 0 THEN abs(under_price)/(abs(under_price)+100.0)
                                 ELSE 100.0/(under_price+100.0) END), 0)
                   END AS p_over_devig
            FROM close_{market}
        """)
        frames.append(f"SELECT * FROM quotes_{market}")

    con.execute("CREATE OR REPLACE TABLE quotes_all AS " + " UNION ALL ".join(frames))
    summary = con.execute("""
        SELECT market_key, count(*) AS book_quotes,
               count(DISTINCT event_id || '|' || player_name) AS event_players,
               round(100.0*avg(CASE WHEN two_sided THEN 1.0 ELSE 0 END), 1) AS pct_two_sided,
               round(avg(line), 3) AS avg_line
        FROM quotes_all GROUP BY 1 ORDER BY 1
    """).fetchdf()
    log.info("book-level quotes:\n%s", summary.to_string(index=False))


# ── step 5: leak-safe pregame features ─────────────────────────────────────────

def build_rolling_features(con, source_relation: str) -> None:
    """Collapse hand-split rows, then LAG one game per batter.

    `source_relation` is any SQL expression valid in a FROM clause, so this is
    exercisable against an in-memory fixture as well as the S3 read — which is what
    lets the switch-hitter leakage guard be RED-provable without network IO.
    """
    # ⚠️⚠️ `mart_batter_rolling_stats` is NOT grained (game_pk, batter_id) despite
    # being documented as "batter × game".  Its true grain is
    # (game_pk, batter_id, BATTER_HAND): a SWITCH-HITTER bats R against one pitcher
    # and L against another in the SAME game and gets TWO rows that SPLIT that
    # game's PAs (measured 2025: 2,598 of 48,840 batter-games ≈ 5.3%).
    #
    # This is a LEAKAGE vector, not just a duplicate-row nuisance: lag() partitioned
    # by batter_id ordered by game_date would, for a switch-hitter, return THE SAME
    # GAME's other-hand row as the "previous game" — i.e. the pregame feature would
    # carry CURRENT-GAME information.  So the hands must be collapsed BEFORE lagging.
    #
    # Collapse rule, measured against the data:
    #   • the _7d/_14d/_30d rolling windows are BATTER-level and are byte-identical
    #     across the two hand rows → max() is exact, not a choice.
    #   • the _std (season-to-date) columns are HAND-CONDITIONAL and genuinely differ
    #     → PA-weighted mean reconstructs the batter-level season-to-date rate.
    #     Picking a row arbitrarily would silently bias these by handedness.
    con.execute(f"""
        CREATE OR REPLACE TABLE rolling_by_game AS
        SELECT game_pk::BIGINT   AS game_pk,
               batter_id::BIGINT AS batter_id,
               any_value(game_date)::DATE AS game_date,
               CASE WHEN count(DISTINCT batter_hand) > 1 THEN 'S'
                    ELSE any_value(batter_hand) END       AS batter_hand,
               any_value(opposing_team)                   AS opposing_team,
               sum(pa_count)                              AS pa_count_game,
               -- batter-level windows: identical across hand rows
               max(pa_count_7d) AS pa_count_7d, max(pa_count_30d) AS pa_count_30d,
               max(games_30d)   AS games_30d,
               max(avg_30d) AS avg_30d, max(obp_30d) AS obp_30d,
               max(slg_30d) AS slg_30d, max(ops_30d) AS ops_30d,
               max(woba_30d) AS woba_30d, max(xwoba_30d) AS xwoba_30d,
               max(xba_30d) AS xba_30d, max(xslg_30d) AS xslg_30d,
               max(k_pct_30d) AS k_pct_30d, max(bb_pct_30d) AS bb_pct_30d,
               max(hard_hit_pct_30d) AS hard_hit_pct_30d,
               max(barrel_pct_30d) AS barrel_pct_30d,
               max(woba_7d) AS woba_7d, max(slg_7d) AS slg_7d,
               max(k_pct_7d) AS k_pct_7d,
               -- hand-conditional season-to-date: PA-weighted to batter level
               sum(woba_std  * pa_count) / nullif(sum(pa_count), 0) AS woba_std,
               sum(slg_std   * pa_count) / nullif(sum(pa_count), 0) AS slg_std,
               sum(iso_std   * pa_count) / nullif(sum(pa_count), 0) AS iso_std,
               sum(k_pct_std * pa_count) / nullif(sum(pa_count), 0) AS k_pct_std
        FROM {source_relation}
        GROUP BY 1, 2
    """)

    # LAG one game per batter: the rolling windows are inclusive of the current
    # game, so the previous game's row is the newest strictly-pregame value.
    con.execute(f"""
        CREATE OR REPLACE TABLE feat_rolling AS
        SELECT game_pk, batter_id, batter_hand, opposing_team,
               prev_pa_count_7d, prev_pa_count_30d, prev_games_30d,
               prev_avg_30d, prev_obp_30d, prev_slg_30d, prev_ops_30d,
               prev_woba_30d, prev_xwoba_30d, prev_xba_30d, prev_xslg_30d,
               prev_k_pct_30d, prev_bb_pct_30d,
               prev_hard_hit_pct_30d, prev_barrel_pct_30d,
               prev_woba_7d, prev_slg_7d, prev_k_pct_7d,
               prev_woba_std, prev_slg_std, prev_iso_std, prev_k_pct_std
        FROM (
            SELECT game_pk, batter_id, batter_hand, opposing_team,
                   lag(pa_count_7d)        OVER w AS prev_pa_count_7d,
                   lag(pa_count_30d)       OVER w AS prev_pa_count_30d,
                   lag(games_30d)          OVER w AS prev_games_30d,
                   lag(avg_30d)            OVER w AS prev_avg_30d,
                   lag(obp_30d)            OVER w AS prev_obp_30d,
                   lag(slg_30d)            OVER w AS prev_slg_30d,
                   lag(ops_30d)            OVER w AS prev_ops_30d,
                   lag(woba_30d)           OVER w AS prev_woba_30d,
                   lag(xwoba_30d)          OVER w AS prev_xwoba_30d,
                   lag(xba_30d)            OVER w AS prev_xba_30d,
                   lag(xslg_30d)           OVER w AS prev_xslg_30d,
                   lag(k_pct_30d)          OVER w AS prev_k_pct_30d,
                   lag(bb_pct_30d)         OVER w AS prev_bb_pct_30d,
                   lag(hard_hit_pct_30d)   OVER w AS prev_hard_hit_pct_30d,
                   lag(barrel_pct_30d)     OVER w AS prev_barrel_pct_30d,
                   lag(woba_7d)            OVER w AS prev_woba_7d,
                   lag(slg_7d)             OVER w AS prev_slg_7d,
                   lag(k_pct_7d)           OVER w AS prev_k_pct_7d,
                   lag(woba_std)           OVER w AS prev_woba_std,
                   lag(slg_std)            OVER w AS prev_slg_std,
                   lag(iso_std)            OVER w AS prev_iso_std,
                   lag(k_pct_std)          OVER w AS prev_k_pct_std
            FROM rolling_by_game
            WINDOW w AS (PARTITION BY batter_id ORDER BY game_date, game_pk)
        )
    """)
    # Guard the invariant this whole block exists to establish: exactly one
    # pregame feature row per (game_pk, batter_id).  A future upstream grain change
    # must fail loudly here, not silently fan the substrate out again.
    fan = con.execute("""
        SELECT count(*) FROM (
            SELECT game_pk, batter_id FROM feat_rolling
            GROUP BY 1, 2 HAVING count(*) > 1)
    """).fetchone()[0]
    if fan:
        raise RuntimeError(
            f"feat_rolling still fans out on {fan} (game_pk, batter_id) keys — "
            "mart_batter_rolling_stats grain changed; fix the collapse before use."
        )


def build_features(con, seasons: list[int]) -> None:
    """Lagged rolling stats + EB posteriors + prior-season park factors."""
    season_list = ",".join(str(s) for s in seasons)
    # Include the season BEFORE the first, so the first games of a season can still
    # take a lagged row from the prior season rather than dropping to NULL.
    lag_seasons = ",".join(str(s) for s in ([min(seasons) - 1] + list(seasons)))

    build_rolling_features(con, f"""(
        SELECT * FROM read_parquet(
            '{LAKEHOUSE}/mart_batter_rolling_stats/**/*.parquet', union_by_name=true)
        WHERE game_year IN ({lag_seasons}))""")

    # EB posteriors are already pregame (confirmed-lineup build).  game_pk/batter_id
    # are VARCHAR in this table — cast both sides explicitly.
    con.execute(f"""
        CREATE OR REPLACE TABLE feat_eb AS
        SELECT game_pk::BIGINT   AS game_pk,
               batter_id::BIGINT AS batter_id,
               batting_slot::INTEGER AS batting_slot,
               eb_woba, eb_k_pct, eb_bb_pct, eb_iso,
               eb_woba_uncertainty, pa_weight, eb_data_source
        FROM read_parquet('{LAKEHOUSE}/eb_batter_posteriors_raw/**/*.parquet',
                          union_by_name=true)
        WHERE season IN ({season_list})
    """)

    # Park factors joined on the PRIOR season (current-season factors embed the
    # season being predicted).
    con.execute(f"""
        CREATE OR REPLACE TABLE feat_park AS
        SELECT venue_id::BIGINT AS venue_id,
               (season + 1)::INTEGER AS apply_season,
               eb_hr_factor, eb_singles_factor, eb_doubles_triples_factor,
               eb_woba_factor, eb_so_factor, eb_bb_factor
        FROM read_parquet('{LAKEHOUSE}/mart_park_factors_granular/**/*.parquet',
                          union_by_name=true)
    """)
    for t in ("feat_rolling", "feat_eb", "feat_park"):
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        log.info("  %-14s %s rows", t, f"{n:,}")


# ── step 6: assemble ───────────────────────────────────────────────────────────

def assemble(con) -> pd.DataFrame:
    """Join everything to one row per (game_pk, batter_id, market_key)."""
    con.execute("""
        CREATE OR REPLACE TABLE substrate AS
        WITH quoted AS (
            -- BOOK-level quotes → game_pk (via event_map) and → candidate batter_ids
            SELECT q.*, em.game_pk, em.season, em.resolver AS event_resolver,
                   nc.batter_id, nc.match_tier AS name_match_tier
            FROM quotes_all q
            JOIN event_map em      ON em.event_id = q.event_id
                                  AND em.game_pk IS NOT NULL
            JOIN name_candidates nc ON nc.player_name = q.player_name
        ),
        -- APPEARANCE ARBITRATION: keep only the candidate id that actually batted
        -- in that game.  This is what makes the last-initial fallback safe.
        resolved AS (
            SELECT q.*, o.game_date,
                   o.pa, o.hits, o.home_runs, o.total_bases,
                   o.singles, o.doubles, o.triples, o.walks, o.strikeouts
            FROM quoted q
            JOIN outcomes o USING (game_pk, batter_id)
        ),
        -- A name that still maps to >1 id WITHIN one game/market is genuinely
        -- ambiguous (both players batted) — drop it rather than guess.
        unambiguous AS (
            SELECT * FROM (
                SELECT *, count(DISTINCT batter_id) OVER (
                    PARTITION BY game_pk, market_key, player_name) AS n_ids_in_game
                FROM resolved
            ) WHERE n_ids_in_game = 1
        ),
        -- ONE quote per (batter-game, market, BOOK).  Two name spellings for the same
        -- batter are the same book's single opinion, not two — collapse them here so
        -- the consensus below pools books rather than double-counting one.
        per_book AS (
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY game_pk, batter_id, market_key, bookmaker_key
                    ORDER BY two_sided DESC, p_over_devig NULLS LAST, line) AS rn
                FROM unambiguous
            ) WHERE rn = 1
        ),
        -- NOW form the consensus, keyed on the RESOLVED identity.
        deduped AS (
            SELECT game_pk, batter_id, market_key,
                   any_value(season)          AS season,
                   any_value(game_date)       AS game_date,
                   any_value(event_id)        AS event_id,
                   min(player_name)           AS player_name,
                   any_value(event_resolver)  AS event_resolver,
                   min(name_match_tier)       AS name_match_tier,
                   any_value(pa) AS pa, any_value(hits) AS hits,
                   any_value(home_runs) AS home_runs, any_value(total_bases) AS total_bases,
                   any_value(singles) AS singles, any_value(doubles) AS doubles,
                   any_value(triples) AS triples, any_value(walks) AS walks,
                   any_value(strikeouts) AS strikeouts,
                   median(line)                                   AS line_consensus,
                   nullif(stddev(line), 0)                        AS line_std,
                   count(DISTINCT bookmaker_key)                  AS n_books,
                   sum(CASE WHEN two_sided THEN 1 ELSE 0 END)     AS n_books_two_sided,
                   avg(p_over_devig)                              AS p_over_consensus,
                   nullif(stddev(p_over_devig), 0)                AS p_over_std
            FROM per_book
            GROUP BY 1, 2, 3
        )
        SELECT
            d.game_pk, d.batter_id, d.market_key, d.season, d.game_date,
            d.event_id, d.player_name, d.event_resolver, d.name_match_tier,
            -- realized outcomes
            d.pa, d.hits, d.home_runs, d.total_bases,
            d.singles, d.doubles, d.triples, d.walks, d.strikeouts,
            CASE d.market_key WHEN 'batter_hits'        THEN d.hits
                              WHEN 'batter_home_runs'   THEN d.home_runs
                              WHEN 'batter_total_bases' THEN d.total_bases END AS y_actual,
            -- market benchmark (NOT a fit target)
            d.line_consensus, d.line_std, d.n_books, d.n_books_two_sided,
            d.p_over_consensus, d.p_over_std,
            CASE WHEN d.p_over_consensus IS NOT NULL THEN
                CASE d.market_key WHEN 'batter_hits'        THEN d.hits
                                  WHEN 'batter_home_runs'   THEN d.home_runs
                                  WHEN 'batter_total_bases' THEN d.total_bases END
                > d.line_consensus END                                        AS y_over,
            -- pregame features
            r.* EXCLUDE (game_pk, batter_id),
            e.* EXCLUDE (game_pk, batter_id),
            p.* EXCLUDE (venue_id, apply_season),
            s.venue_id, s.official_date
        FROM deduped d
        LEFT JOIN feat_rolling r USING (game_pk, batter_id)
        LEFT JOIN feat_eb      e USING (game_pk, batter_id)
        LEFT JOIN spine        s ON s.game_pk = d.game_pk
        LEFT JOIN feat_park    p ON p.venue_id = s.venue_id
                                AND p.apply_season = d.season
    """)
    # ⭐ GRAIN GUARD — the substrate's declared grain is (game_pk, batter_id,
    # market_key) and NOTHING downstream re-checks it.  The first published artifact
    # shipped 11,461 duplicate keys (two name spellings for one batter) and it was
    # caught only by reading the artifact back afterwards.  Fail the BUILD instead.
    fan = con.execute("""
        SELECT count(*) FROM (
            SELECT game_pk, batter_id, market_key FROM substrate
            GROUP BY 1, 2, 3 HAVING count(*) > 1)
    """).fetchone()[0]
    if fan:
        raise RuntimeError(
            f"substrate fans out on {fan} (game_pk, batter_id, market_key) keys — "
            "the declared grain is violated; do NOT publish. Most likely two "
            "player_name spellings resolving to one batter_id (see build_lines)."
        )
    return con.execute("SELECT * FROM substrate").fetchdf()


def report(con) -> None:
    log.info("── substrate summary ──")
    for sql, title in [
        ("""SELECT market_key, season, count(*) AS n,
                   round(avg(y_actual), 3) AS mean_y,
                   round(100.0*avg(CASE WHEN y_actual=0 THEN 1.0 ELSE 0 END),1) AS pct_zero,
                   round(100.0*avg(CASE WHEN p_over_consensus IS NOT NULL
                                        THEN 1.0 ELSE 0 END),1) AS pct_devigged
            FROM substrate GROUP BY 1,2 ORDER BY 1,2""", "rows by market × season"),
        ("""SELECT event_resolver, name_match_tier, count(*) AS n
            FROM substrate GROUP BY 1,2 ORDER BY n DESC""", "join provenance"),
        ("""SELECT market_key,
                   round(100.0*avg(CASE WHEN prev_woba_30d IS NOT NULL THEN 1.0 ELSE 0 END),1) AS pct_rolling,
                   round(100.0*avg(CASE WHEN eb_woba       IS NOT NULL THEN 1.0 ELSE 0 END),1) AS pct_eb,
                   round(100.0*avg(CASE WHEN eb_hr_factor  IS NOT NULL THEN 1.0 ELSE 0 END),1) AS pct_park
            FROM substrate GROUP BY 1 ORDER BY 1""", "feature coverage"),
    ]:
        log.info("%s:\n%s", title, con.execute(sql).fetchdf().to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", default=",".join(str(s) for s in ALL_SEASONS),
                    help="Comma-separated seasons (default: all).")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Output parquet path (s3:// or local).")
    ap.add_argument("--smoke", action="store_true",
                    help="Report only; do NOT write the parquet.")
    ap.add_argument("--memory-limit-gb", type=int, default=8)
    args = ap.parse_args()

    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    con = connect(args.memory_limit_gb)

    log.info("seasons=%s", seasons)
    build_outcomes(con, seasons)
    build_event_map(con, seasons)
    build_name_map(con, seasons)
    build_lines(con, seasons)
    build_features(con, seasons)
    df = assemble(con)
    report(con)

    log.info("substrate: %s rows × %s cols", f"{len(df):,}", df.shape[1])
    if args.smoke:
        log.info("--smoke: not writing.  Output would be → %s", args.out)
        return
    con.execute(f"COPY substrate TO '{args.out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    log.info("wrote → %s", args.out)


if __name__ == "__main__":
    main()
