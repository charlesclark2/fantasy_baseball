"""crosswalk.py — NF-W0b: the maintained canonical crosswalk (v3 §12A's field contract).

`canonical_player_id` IS the nflverse `gsis_id`. That is a decision, not an accident: every
downstream consumer in the repo — `fct_player_week.player_id`, `season_projection`,
`export_draft_board_json`, the Sleeper/ESPN import bridges — already keys on it, so minting a
fresh surrogate would orphan all of them for no resolution gain. §12A's canonical-id requirement
is satisfied by NAMING the existing key and maintaining the vendor map around it.

Two tiers of content, deliberately separate:

  • DERIVED (tier 1 of the ladder) — `build_crosswalk` unpivots the vendor-id columns
    `weekly_rosters` already carries (espn / sportradar / yahoo / rotowire / pff / pfr /
    fantasy_data / sleeper / esb / smart / gsis_it) into one row per
    (canonical_player_id, source_name, source_player_id) segment. `match_method` is
    `stable_vendor_id`, confidence 1.0, `review_status='auto'`. This is regenerated from the lake
    and must never be hand-edited.

  • REVIEWED (tier 2) — `load_reviewed_crosswalk` reads a small, hand-maintained CSV of overrides
    for identities the ladder cannot reach or got wrong. It OUTRANKS every automatic rung below
    tier 1, which is the point: a human decision must not be re-litigated by a fuzzy score on the
    next run. Rows are `review_status='reviewed'`, confidence 0.99.

⚠️ THE VENDOR-ID MAP IS NOT DENSE, AND THAT IS THE STORY'S WHOLE PREMISE. Measured 2022–2025 on
the live lake, `weekly_rosters.pfr_id` is **25–53% NULL** — so a tier-1-only bridge resolves only
~66% of 2024 snap players. The crosswalk therefore reports its own coverage
(`vendor_id_coverage`) rather than being assumed dense; a consumer that treats a sparse vendor
column as a complete key is exactly how a miss becomes a silent zero.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .names import normalize_name, normalize_team, position_group

log = logging.getLogger("nfl.entity.crosswalk")

# The §12A canonical crosswalk field contract, in order. Pinned by a guard test so a field cannot
# be quietly dropped from the artifact.
CROSSWALK_COLUMNS: tuple[str, ...] = (
    "canonical_player_id",
    "source_name",
    "source_player_id",
    "source_player_name",
    "normalized_name",
    "team_id",
    "position",
    "effective_start_timestamp",
    "effective_end_timestamp",
    "match_method",
    "match_confidence",
    "review_status",
    "last_verified_timestamp",
)

# `weekly_rosters` vendor-id column → §12A `source_name`. `gsis_it_id` is nflverse's own second
# id space and is carried too: it is a stable vendor id like any other, and a consumer keyed on it
# should resolve at tier 1 rather than fall to a name match.
VENDOR_ID_COLUMNS: dict[str, str] = {
    "espn_id": "espn",
    "sportradar_id": "sportradar",
    "yahoo_id": "yahoo",
    "rotowire_id": "rotowire",
    "pff_id": "pff",
    "pfr_id": "pfr",
    "fantasy_data_id": "fantasy_data",
    "sleeper_id": "sleeper",
    "esb_id": "esb",
    "smart_id": "smart",
    "gsis_it_id": "gsis_it",
}

REVIEWED_CROSSWALK_PATH = Path(__file__).resolve().parent / "reviewed_crosswalk.csv"


def empty_crosswalk() -> pd.DataFrame:
    """An empty crosswalk carrying the full §12A column contract (the no-data-yet shape)."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in CROSSWALK_COLUMNS})


def _clean_id(s: pd.Series) -> pd.Series:
    """Vendor ids arrive as float/int/str across seasons (the N0.2 type-drift). Render to a stable
    string and blank out the values that are 'present but meaningless' — `None`, empty, and the
    float artefacts `nan` / `0` / `0.0` that a numeric column produces for a missing id. Blanking
    is the SAFE direction: a blanked id resolves at a lower rung, whereas a '0.0' treated as a real
    id would merge every id-less player of that vendor into one canonical player."""
    out = s.astype("string").str.strip()
    out = out.str.replace(r"\.0$", "", regex=True)
    return out.mask(out.isin(["", "nan", "None", "<NA>", "0", "-1"]) | out.isna(), pd.NA)


def build_crosswalk(
    rosters: pd.DataFrame,
    *,
    last_verified_timestamp: str,
    sources: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Unpivot `weekly_rosters`' vendor-id columns into the §12A crosswalk (tier-1 content).

    `rosters` needs `gsis_id` plus any of `VENDOR_ID_COLUMNS`; `season`, `week`, `team`,
    `position`, and a name column are used when present. `week_start_et`/`week_end_et` become the
    real `effective_*_timestamp`s; when absent they are left NULL rather than back-filled with a
    fabricated season boundary — a made-up validity window is worse than a missing one, because a
    later point-in-time read would trust it.

    One row per (canonical_player_id, source_name, source_player_id, team_id, position) segment,
    with the effective window spanning that segment's weeks.
    """
    sources = sources or VENDOR_ID_COLUMNS
    if rosters is None or rosters.empty or "gsis_id" not in rosters.columns:
        return empty_crosswalk()

    df = rosters.copy()
    df["canonical_player_id"] = _clean_id(df["gsis_id"])
    df = df[df["canonical_player_id"].notna()]
    if df.empty:
        return empty_crosswalk()

    name_col = next(
        (c for c in ("full_name", "player_name", "player", "display_name") if c in df.columns), None
    )
    df["_name"] = df[name_col].astype("string") if name_col else pd.NA
    df["_team"] = (
        df["team"].map(normalize_team) if "team" in df.columns else pd.Series("", index=df.index)
    )
    df["_pos"] = (
        df["position"].map(position_group) if "position" in df.columns else pd.Series("", index=df.index)
    )
    has_window = {"week_start_et", "week_end_et"} <= set(df.columns)

    frames: list[pd.DataFrame] = []
    for col, source_name in sources.items():
        if col not in df.columns:
            continue
        sub = df[["canonical_player_id", "_name", "_team", "_pos"]].copy()
        sub["source_player_id"] = _clean_id(df[col])
        if has_window:
            sub["_start"] = df["week_start_et"]
            sub["_end"] = df["week_end_et"]
        sub = sub[sub["source_player_id"].notna()]
        if sub.empty:
            continue
        sub["source_name"] = source_name
        frames.append(sub)

    if not frames:
        return empty_crosswalk()

    allrows = pd.concat(frames, ignore_index=True)
    keys = ["canonical_player_id", "source_name", "source_player_id", "_team", "_pos"]
    agg: dict[str, tuple] = {"_name": ("_name", "first")}
    if has_window:
        agg["_start"] = ("_start", "min")
        agg["_end"] = ("_end", "max")
    grouped = allrows.groupby(keys, dropna=False, as_index=False).agg(**agg)

    out = pd.DataFrame(
        {
            "canonical_player_id": grouped["canonical_player_id"],
            "source_name": grouped["source_name"],
            "source_player_id": grouped["source_player_id"],
            "source_player_name": grouped["_name"],
            "normalized_name": grouped["_name"].map(normalize_name),
            "team_id": grouped["_team"],
            "position": grouped["_pos"],
            "effective_start_timestamp": grouped["_start"] if has_window else pd.NA,
            "effective_end_timestamp": grouped["_end"] if has_window else pd.NA,
            "match_method": "stable_vendor_id",
            "match_confidence": 1.0,
            "review_status": "auto",
            "last_verified_timestamp": last_verified_timestamp,
        }
    )
    return out[list(CROSSWALK_COLUMNS)].reset_index(drop=True)


def load_reviewed_crosswalk(path: str | Path | None = None) -> pd.DataFrame:
    """Load the hand-maintained tier-2 overrides. Missing/empty file → an empty crosswalk.

    Only `canonical_player_id`, `source_name` and `source_player_id` are required in the file;
    every other §12A column is filled with the reviewed defaults so a maintainer writes three
    columns rather than thirteen.
    """
    p = Path(path) if path is not None else REVIEWED_CROSSWALK_PATH
    if not p.exists():
        return empty_crosswalk()
    df = pd.read_csv(p, dtype=str, comment="#")
    if df.empty:
        return empty_crosswalk()
    required = {"canonical_player_id", "source_name", "source_player_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"reviewed crosswalk {p} is missing required columns: {sorted(missing)}")
    for c in CROSSWALK_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df["match_method"] = "reviewed_crosswalk"
    df["match_confidence"] = pd.to_numeric(df["match_confidence"], errors="coerce").fillna(0.99)
    df["review_status"] = df["review_status"].fillna("reviewed")
    df["normalized_name"] = df["normalized_name"].fillna(
        df["source_player_name"].map(normalize_name)
    )
    df["source_player_id"] = _clean_id(df["source_player_id"])
    return df[list(CROSSWALK_COLUMNS)].reset_index(drop=True)


def vendor_id_coverage(rosters: pd.DataFrame, *, by: str = "season") -> pd.DataFrame:
    """Per-vendor non-null share of each id column — the diagnostic that stops a consumer treating
    a sparse vendor column as a complete key (the `pfr_id` 25–53%-NULL trap this story exists for).
    """
    if rosters is None or rosters.empty:
        return pd.DataFrame(columns=[by, "source_name", "n_rows", "n_present", "coverage"])
    rows = []
    grouper = rosters.groupby(by) if by in rosters.columns else [(None, rosters)]
    for key, sub in grouper:
        for col, source_name in VENDOR_ID_COLUMNS.items():
            if col not in sub.columns:
                continue
            present = int(_clean_id(sub[col]).notna().sum())
            rows.append(
                {
                    by: key,
                    "source_name": source_name,
                    "n_rows": int(len(sub)),
                    "n_present": present,
                    "coverage": round(present / max(1, len(sub)), 4),
                }
            )
    return pd.DataFrame(rows)
