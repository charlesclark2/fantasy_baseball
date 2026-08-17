"""contract_source.py — NF-D8 CONTRACT / FINANCIAL feature source (salary as a team-investment
proxy + positional cap investment).

THE LEVER (from the operator's NotebookLM feature scan): player CONTRACT $ is the team's OWN
forward projection of the player — an insider/revealed-belief signal, cited in the research to
explain ~41% of YoY fantasy-performance variance with ZERO on-field stats. It is market-ADJACENT
but NOT the betting/consensus market (team investment ≠ ADP/ECR), so it stays market-blind-SAFE
for NF1.2/NF1.5. AGGREGATE positional cap investment (e.g. total O-line cap) is also the cheap,
concrete proxy for surrounding-scheme quality NF1.2's H-OLINE hand-waved.

DATA SOURCE (live-probed, not coded to docs — see the module footnote): OverTheCap.com's own
site disallows the Anthropic-AI crawler in `robots.txt`, and Spotrac hard-blocks automated
fetches — so we do NOT scrape either site directly. Instead we read **nflverse's own
`historical_contracts.parquet` release** (`nflverse/nflverse-data`, tag `contracts`,
CC-BY-4.0) — the SAME upstream vendor this repo already trusts for `nfl/raw/pbp` / `rosters` /
`snap_counts` (`defense_source.py` / `xfp_source.py`), who fetch + redistribute the OTC contract
data themselves via `nflreadr::load_contracts()`. One file, ~52k contracts, 2005–2026,
`gsis_id` already populated (~92% coverage) in the EXACT format our marts' `player_id` uses
(`fct_player_week.player_id`) — a direct join, no fuzzy name crosswalk needed (unlike
`adp_source.py`'s FFC crosswalk).

THE CONSTRUCT (leakage-safe as-of preseason):

  1. FLATTEN — each contract carries a nested per-year `cols` array (cap_number / base_salary /
     guaranteed_salary per season of the deal, plus a synthetic 'Total' rollup row we drop).
     `flatten_contract_years` explodes this to one row per (contract, year).

  2. AS-OF-PRESEASON SELECTION — for projecting `season`, only contracts SIGNED ON/BEFORE
     `season` are eligible (`year_signed <= season` — free-agent deals sign in the March–August
     offseason and rookie deals slot within weeks of the draft, both well before Week 1, the
     same preseason-known posture NF-D1/NF-D2/`adp_source` use). Where multiple contracts have a
     `year == season` entry (an extension superseding an older deal's now-void out-year),
     `active_contract_rows` keeps the MOST RECENTLY SIGNED one.

  3. FEATURES — per-player: this season's cap hit / base salary / guaranteed $, the contract-
     level `guaranteed_ratio` (guaranteed ÷ total value) and the cited non-linear form
     `log(apy) × guaranteed_ratio` (handed to the model directly — NF1.5's guidance is a GBM
     finds most interactions itself, but this one encodes domain structure worth pre-computing).
     Per-team (`team_cap_aggregates`): total committed cap (the payroll-proxy denominator),
     O-LINE cap total + share (C/LG/RG/LT/RT — the concrete H-OLINE blocking-quality proxy), and
     SKILL-position cap CONCENTRATION (a Herfindahl index over QB/RB/WR/TE cap shares — investment
     concentrated in a few stars vs spread through the room).

DELIVERABLE: `load_contract_features(season)` → one row per player with the financial features
AND the team aggregates already merged in (the join contract NF1.2/NF1.5 consume, mirroring
`defense_source.load_forward_defense` / `xfp_source.load_xfp_features`), read from the landed
Delta `nfl/fantasy/contracts/player_contract_features` if present, else computed on the fly.
`load_team_cap_aggregates(season)` exposes the team-level table directly. Edge-independent,
`best_alpha=0` — a projection FEATURE, not an edge claim; the lift is proven downstream in
NF1.2/NF1.5's ablation, not asserted here.

Pure helpers (`team_abbr`, `flatten_contract_years`, `active_contract_rows`,
`team_cap_aggregates`, `guaranteed_ratio`, `log_investment_feature`) take DataFrames/arrays in
and out with NO IO, so the construct is unit-tested offline against the fast gate; the network
fetch + the crosswalk match-rate diagnostic live in `fetch_historical_contracts` / `coverage_report`.
"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.contract")

_ART = Path(__file__).resolve().parent / "artifacts"
_DEFAULT_CACHE = _ART / "contract_cache"

# The nflverse release asset (see module docstring — NOT overthecap.com/spotrac.com directly).
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"

# The landed contract-feature Delta tables (the serving deliverables).
LAKE_SPORT = "nfl"
LAKE_TIER = "fantasy"
LAKE_SOURCE_PLAYER = "contracts/player_contract_features"
LAKE_SOURCE_TEAM = "contracts/team_cap_aggregates"

# Position groups (vocabulary probed live from the actual data — NOT assumed): the contracts
# dataset splits the O-line into individual spots (no generic "OL"/"G"/"T"), which is even more
# precise than a coarse group for the H-OLINE proxy.
OL_POSITIONS = frozenset({"C", "LG", "RG", "LT", "RT"})
SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})

# nflverse contracts nickname → standard team abbreviation (the crosswalk landmine
# `sport_data_platform.md` warns about — this source keys teams by NICKNAME, e.g. "Bengals", not
# the abbreviation our marts/PBP use, e.g. "CIN"). 32 current teams + legacy-franchise aliases
# (Washington's renames; the pre-1997 Houston "Oilers" → Tennessee lineage, immaterial to the
# seasons this module actually projects but kept so a raw contract row is never silently dropped).
_TEAM_ABBR = {
    "49ers": "SF", "Bears": "CHI", "Bengals": "CIN", "Bills": "BUF", "Broncos": "DEN",
    "Browns": "CLE", "Buccaneers": "TB", "Cardinals": "ARI", "Chargers": "LAC", "Chiefs": "KC",
    "Colts": "IND", "Commanders": "WAS", "Cowboys": "DAL", "Dolphins": "MIA", "Eagles": "PHI",
    "Falcons": "ATL", "Giants": "NYG", "Jaguars": "JAX", "Jets": "NYJ", "Lions": "DET",
    "Oilers": "TEN", "Packers": "GB", "Panthers": "CAR", "Patriots": "NE", "Raiders": "LV",
    "Rams": "LAR", "Ravens": "BAL", "Redskins": "WAS", "Saints": "NO", "Seahawks": "SEA",
    "Steelers": "PIT", "Texans": "HOU", "Titans": "TEN", "Vikings": "MIN", "Washington": "WAS",
}

# A parsed `cols[i].year` outside this range is a raw-data artifact (a handful of futures/
# practice-squad rows carry a truncated '201' or placeholder '0' year — probed live, see
# run_contract_ingest.py --probe), not a real season; Matthew Stafford's void-year accounting
# legitimately reaches 2038 and Dan Marino/Steve Young's real career years reach back to the
# 1980s, so the bounds are wide on purpose — this only screens out garbage, not history.
_MIN_VALID_YEAR, _MAX_VALID_YEAR = 1980, 2045

_CONTRACT_COLS = ("gsis_id", "player", "position", "year_signed", "years", "value", "apy",
                  "guaranteed", "otc_id", "is_active")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers (no IO — fast-gate tested)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def team_abbr(nickname: str) -> str | None:
    """Nickname (e.g. 'Bengals') → standard team abbreviation (e.g. 'CIN'). An unrecognized
    nickname (a data artifact, or the synthetic 'Total' rollup label) → None. PURE."""
    return _TEAM_ABBR.get((nickname or "").strip())


def flatten_contract_years(contracts: pd.DataFrame) -> pd.DataFrame:
    """Explode each contract's nested per-year `cols` array into one row per (contract, year),
    carrying the contract-level columns (`gsis_id`, `player`, `position`, `year_signed`, `years`,
    `value`, `apy`, `guaranteed`, `otc_id`, `is_active`) through onto every year row. Drops the
    synthetic 'Total' rollup entry every contract's `cols` carries and any row whose year parses
    outside `[_MIN_VALID_YEAR, _MAX_VALID_YEAR]` (raw-data artifacts — see the module docstring).
    PURE (a plain DataFrame → DataFrame transform; no network/DB)."""
    cols_out = [*_CONTRACT_COLS, "year", "team_abbr", "cap_number", "base_salary",
                "guaranteed_salary", "cap_percent"]
    if contracts is None or contracts.empty:
        return pd.DataFrame(columns=cols_out)

    rows = []
    for c in contracts.itertuples(index=False):
        arr = getattr(c, "cols", None)
        if arr is None:
            continue
        base = {k: getattr(c, k) for k in _CONTRACT_COLS}
        for yr in arr:
            y = yr.get("year")
            if y is None or y == "Total":
                continue
            try:
                year_int = int(y)
            except (TypeError, ValueError):
                continue
            if not (_MIN_VALID_YEAR <= year_int <= _MAX_VALID_YEAR):
                continue
            row = dict(base)
            row["year"] = year_int
            row["team_abbr"] = team_abbr(yr.get("team"))
            row["cap_number"] = yr.get("cap_number")
            row["base_salary"] = yr.get("base_salary")
            row["guaranteed_salary"] = yr.get("guaranteed_salary")
            row["cap_percent"] = yr.get("cap_percent")
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=cols_out)
    out = pd.DataFrame(rows, columns=cols_out)
    for c in ("cap_number", "base_salary", "guaranteed_salary", "cap_percent", "value", "apy",
             "guaranteed", "years", "year_signed"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def active_contract_rows(flat: pd.DataFrame, season: int) -> pd.DataFrame:
    """The AS-OF-PRESEASON active contract-year row for each player projecting `season`: among
    every contract SIGNED ON/BEFORE `season` (`year_signed <= season` — leakage-safe, the deal is
    public knowledge before Week 1) that has a `year == season` entry, keep the MOST RECENTLY
    SIGNED contract per `gsis_id` (a later extension supersedes an older deal's now-void out-year
    row for the same season). Rows with no `gsis_id` are dropped (nothing to join to our marts
    on). One row per `gsis_id`. PURE."""
    d = flat[(flat["year"] == int(season)) & (flat["year_signed"] <= int(season))
            & flat["gsis_id"].notna()].copy()
    if d.empty:
        return d
    d = d.sort_values(["gsis_id", "year_signed", "otc_id"], ascending=[True, False, False])
    return d.drop_duplicates(subset="gsis_id", keep="first").reset_index(drop=True)


def team_cap_aggregates(active: pd.DataFrame) -> pd.DataFrame:
    """Per-team season cap-investment aggregates from the active-contract-year rows: total
    committed cap (the payroll-proxy denominator — sum of every listed player's `cap_number`),
    O-LINE cap total + share (C/LG/RG/LT/RT — the concrete H-OLINE 'blocking quality' proxy), and
    SKILL-position cap CONCENTRATION (a Herfindahl index — Σ(share²) — over each skill player's
    share of the team's skill-position cap; higher = investment concentrated in a few stars,
    lower = spread through the room). A team with no skill cap (shouldn't happen, but a thin/
    incomplete slice) gets a NaN concentration rather than a divide-by-zero. PURE."""
    cols = ["team_abbr", "team_total_cap", "team_ol_cap_total", "team_ol_cap_pct",
            "team_skill_cap_total", "team_skill_cap_concentration", "n_ol_contracts",
            "n_skill_contracts"]
    d = active.dropna(subset=["team_abbr", "cap_number"])
    if d.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for team, g in d.groupby("team_abbr"):
        total_cap = float(g["cap_number"].sum())
        ol = g[g["position"].isin(OL_POSITIONS)]
        skill = g[g["position"].isin(SKILL_POSITIONS)]
        ol_cap = float(ol["cap_number"].sum())
        skill_cap = float(skill["cap_number"].sum())
        if skill_cap > 0:
            shares = skill["cap_number"].to_numpy(dtype=float) / skill_cap
            hhi = float(np.sum(shares ** 2))
        else:
            hhi = np.nan
        out.append({
            "team_abbr": team, "team_total_cap": total_cap, "team_ol_cap_total": ol_cap,
            "team_ol_cap_pct": ol_cap / total_cap if total_cap > 0 else np.nan,
            "team_skill_cap_total": skill_cap, "team_skill_cap_concentration": hhi,
            "n_ol_contracts": int(len(ol)), "n_skill_contracts": int(len(skill)),
        })
    return pd.DataFrame(out, columns=cols)


def guaranteed_ratio(guaranteed: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Fraction of a contract's total value that is guaranteed (0..1) — a fixed per-contract
    measure of "how guaranteed is this deal" (stabler than a per-year ratio, which is 0 in every
    non-guaranteed out-year even on a huge contract). A contract with 0 (or unknown) total value
    → NaN, never a divide-by-zero. PURE."""
    g = np.asarray(guaranteed, dtype=float)
    v = np.asarray(value, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(v > 0, g / v, np.nan)
    return r


def log_investment_feature(apy: np.ndarray, guaranteed_ratio_: np.ndarray) -> np.ndarray:
    """The cited non-linear investment-proxy form `log(salary) × guaranteed_ratio`, handed to the
    model directly (NF1.5's guidance: a GBM auto-discovers most interactions, so reserve an
    explicit engineered term for domain structure a tree can't easily infer — this one). `apy`
    (the contract's annualized $M value) is floored at a small epsilon before the log (0/negative
    apy is a data artifact, never a real deal) so the feature is always finite. NaN
    `guaranteed_ratio_` (an unknown-value contract) propagates to NaN, not a fabricated 0. PURE."""
    a = np.clip(np.asarray(apy, dtype=float), 1e-3, None)
    r = np.asarray(guaranteed_ratio_, dtype=float)
    return np.log(a) * r


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Network fetch (the nflverse release — cached to parquet, assemble-once)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fetch_historical_contracts(cache_dir: str | Path | None = None, refresh: bool = False,
                               timeout: int = 60) -> pd.DataFrame:
    """Fetch nflverse's `historical_contracts.parquet` release asset (one file, ALL seasons —
    unlike the per-season nflverse pbp/roster assets), caching the raw bytes to `cache_dir` so a
    run is offline-reproducible once primed (assemble-once cost hygiene — every season's feature
    build reads this ONE cached file, never re-fetches). `refresh` forces a re-download (the
    annual new-league-year cadence the story specifies)."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "historical_contracts.parquet"
    if not cache.exists() or refresh:
        req = urllib.request.Request(CONTRACTS_URL, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            cache.write_bytes(resp.read())
        log.info("nflverse contracts cache written: %s", cache)
    return pd.read_parquet(cache)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Assembly — the leakage-safe per-season feature build
# ══════════════════════════════════════════════════════════════════════════════════════════════
_PLAYER_OUT_COLS = [
    "season", "player_id", "player", "position", "team_abbr",
    "year_signed", "years", "value", "apy", "guaranteed", "guaranteed_ratio", "log_investment",
    "cap_number", "base_salary", "guaranteed_salary", "cap_hit_pct_team",
    "team_total_cap", "team_ol_cap_total", "team_ol_cap_pct",
    "team_skill_cap_total", "team_skill_cap_concentration",
]


def build_player_contract_features(active: pd.DataFrame, team_agg: pd.DataFrame,
                                   season: int) -> pd.DataFrame:
    """Per-player financial features for `season` from the active-contract rows, with the
    player's TEAM's aggregate cap columns merged in (so a consumer joins ONCE by `player_id` and
    gets both the individual signal and the surrounding-scheme proxy — the join contract NF1.2/
    NF1.5 use)."""
    if active is None or active.empty:
        return pd.DataFrame(columns=_PLAYER_OUT_COLS)
    d = active.copy()
    d["guaranteed_ratio"] = guaranteed_ratio(d["guaranteed"].to_numpy(), d["value"].to_numpy())
    d["log_investment"] = log_investment_feature(d["apy"].to_numpy(),
                                                 d["guaranteed_ratio"].to_numpy())
    d = d.merge(team_agg, on="team_abbr", how="left")
    d["cap_hit_pct_team"] = np.where(d["team_total_cap"] > 0,
                                     d["cap_number"] / d["team_total_cap"], np.nan)
    d = d.rename(columns={"gsis_id": "player_id"})
    d.insert(0, "season", int(season))
    return d[_PLAYER_OUT_COLS].sort_values(["team_abbr", "position", "player_id"]).reset_index(drop=True)


def build_contract_features(season: int, *, cache_dir: str | Path | None = None,
                            refresh: bool = False,
                            contracts: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute the leakage-safe (year_signed ≤ season) per-player + per-team contract features
    for `season` from the raw nflverse contracts frame (fetched/cached if `contracts` isn't
    passed — e.g. by a caller that already has it loaded, avoiding a re-parse). Returns
    (player_features, team_aggregates); both empty (with columns) if nothing is active that
    season."""
    raw = contracts if contracts is not None else fetch_historical_contracts(cache_dir=cache_dir,
                                                                              refresh=refresh)
    flat = flatten_contract_years(raw)
    active = active_contract_rows(flat, season)
    team_agg = team_cap_aggregates(active)
    player = build_player_contract_features(active, team_agg, season)
    team_out = team_agg.copy()
    team_out.insert(0, "season", int(season))
    return player, team_out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving contract (lake read-through, mirroring defense_source / xfp_source)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _read_lake(season: int, source: str) -> pd.DataFrame | None:
    """Read a landed contract-feature Delta table for `season` from S3. Returns a DataFrame or
    None if the table/partition is absent or the lake is unreachable (mirrors
    `defense_source._read_lake`)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri(LAKE_SPORT, source, tier=LAKE_TIER)
    con = s3io.duckdb_lake_connection()  # INC-45 — the secret channel `delta_scan` actually reads
    try:
        df = con.sql(f"select * from delta_scan('{uri}') where season = {int(season)}").df()
        return df if not df.empty else None
    except Exception as exc:  # noqa: BLE001 — table absent / offline ⇒ caller computes
        log.info("contract lake read unavailable (%s/%s: %s) — will compute", source, season,
                 str(exc)[:120])
        return None
    finally:
        con.close()


def load_contract_features(season: int, *, from_lake: bool = True,
                           cache_dir: str | Path | None = None, refresh: bool = False,
                           contracts: pd.DataFrame | None = None) -> pd.DataFrame:
    """⭐ THE DELIVERABLE — per-player contract/financial-investment features for `season` (the
    player's own cap hit / guaranteed $ / `log_investment`, WITH the team's O-line-cap and
    skill-cap-concentration aggregates already merged in), the way NF1.2/NF1.5 consume it (the
    same load-and-join contract as `defense_source.load_forward_defense` /
    `xfp_source.load_xfp_features`).

    Reads the landed Delta `nfl/fantasy/contracts/player_contract_features` for `season` (the
    fast serving path) if present; else computes on the fly from the (cached) nflverse contracts
    release. Leakage-safe: only contracts signed on/before `season` are used. `best_alpha=0` — a
    projection FEATURE, not an edge claim."""
    if from_lake:
        df = _read_lake(season, LAKE_SOURCE_PLAYER)
        if df is not None:
            return df
    player, _ = build_contract_features(season, cache_dir=cache_dir, refresh=refresh,
                                        contracts=contracts)
    return player


def load_team_cap_aggregates(season: int, *, from_lake: bool = True,
                             cache_dir: str | Path | None = None, refresh: bool = False,
                             contracts: pd.DataFrame | None = None) -> pd.DataFrame:
    """The per-team cap-investment aggregates for `season` on their own (the O-line/skill-
    concentration table `load_contract_features` merges onto every player row) — for a
    team-level consumer, or the coverage/face-validity report."""
    if from_lake:
        df = _read_lake(season, LAKE_SOURCE_TEAM)
        if df is not None:
            return df
    _, team = build_contract_features(season, cache_dir=cache_dir, refresh=refresh,
                                      contracts=contracts)
    return team


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Crosswalk / coverage diagnostics (the sport_data_platform.md join-match-rate check)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def coverage_report(con, player_features: pd.DataFrame, season: int,
                    schema: str = "main_nfl_marts") -> dict:
    """Join match-rate diagnostics for `season`'s contract features vs our own gsis `player_id`
    universe (`fct_player_week`, skill positions only — the population NF1.2/NF1.5 actually
    consume) — the `sport_data_platform.md` crosswalk-landmine check every external source must
    report. A low match rate here (rather than a silently-empty join downstream) is the honest
    signal to investigate before trusting the feature.

    `fct_player_week` carries a row for every player EVER associated with a team's week grid
    (most with `played_flag=False` — a stale historical-roster artifact, not that season's real
    population; e.g. a long-retired player still shows up for a current team-week grain). Filtering
    to `played_flag` (a REAL participant that season) is the same posture NF-D7's
    `_games_per_season` uses for its denominator — the honest, USED-that-season universe, not
    every id the mart has ever seen. (Only meaningful for a COMPLETED season; a not-yet-played
    projection season has 0 played rows by definition — report accordingly.)"""
    ours = con.sql(f"""
        select distinct player_id, position from {schema}.fct_player_week
        where season = {int(season)} and position in ('QB', 'RB', 'WR', 'TE')
          and player_id is not null and coalesce(played_flag, false)
    """).df()
    if ours.empty:
        return {"season": int(season), "n_skill_players_ours": 0, "n_matched": 0,
               "pct_matched": None, "match_rate_by_position": {}, "n_contract_rows": len(player_features)}
    have = set(player_features.get("player_id", pd.Series(dtype=str)).dropna())
    matched = ours["player_id"].isin(have)
    by_pos = ours.assign(matched=matched).groupby("position")["matched"].mean().round(3).to_dict()
    return {
        "season": int(season),
        "n_skill_players_ours": int(len(ours)),
        "n_matched": int(matched.sum()),
        "pct_matched": round(100.0 * float(matched.mean()), 1),
        "match_rate_by_position": by_pos,
        "n_contract_rows": int(len(player_features)),
    }
