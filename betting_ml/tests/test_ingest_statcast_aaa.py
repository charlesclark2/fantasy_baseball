"""E7.2 — fast-gate unit tests for scripts/ingest_statcast_aaa_to_s3.py (pure logic only).

No IO: the module's Delta/S3/Savant paths import deltalake/boto3/duckdb LAZILY inside functions,
so importing the module + exercising transform()/parsers touches no network or S3. Mirrors
test_ingest_milb.py's "fast-gate tests inspect source or import pure logic, never pipeline" rule
(CLAUDE.md) — nothing here imports `pipeline`.
"""
import importlib.util
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "ingest_statcast_aaa_to_s3.py"

_spec = importlib.util.spec_from_file_location("ingest_statcast_aaa_to_s3", _SCRIPT)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ── level / history / cap constants match the verified-live API reality ────────

def test_levels_are_the_two_hawkeye_tiers():
    # Probed live 2026-07-25: the Minors Search's own hfLevel dropdown offers only these two —
    # AA / High-A carry no Hawk-Eye tracking at all.
    assert sc.LEVELS == {
        "AAA": "Triple-A",
        "A": "Single-A / complex (Florida State League + rehab sites)",
    }
    assert sc.DEFAULT_LEVELS == ["AAA"]


def test_earliest_season_floor():
    # Probed live 2026-07-25: 2019/2020/2021 return zero rows for hfLevel=AAA in every month
    # tried. The full backfill's coverage report later showed 2022 already has 96-100% per-park
    # coverage league-wide (statistically indistinguishable from 2023-2026) — there is no
    # meaningful "later full rollout" season to pin, so no FULL_ROLLOUT_SEASON constant exists.
    assert sc.EARLIEST_SEASON == 2022
    assert not hasattr(sc, "FULL_ROLLOUT_SEASON")


def test_row_cap_matches_probed_value():
    # Probed live: the CSV export silently truncates at exactly 10000 rows.
    assert sc.ROW_CAP == 10_000
    assert sc.TRUNCATION_WARN_THRESHOLD < sc.ROW_CAP


def test_savant_base_params_use_minors_and_month_filter():
    # The two undocumented-but-load-bearing params found by live probing: `minors=true` (its
    # absence silently returns a Statcast-shaped header with ZERO rows), and `group_by=name-date`
    # (the finest available grain — the endpoint has no raw pitch-level option at all).
    assert sc.SAVANT_BASE_PARAMS["minors"] == "true"
    assert sc.SAVANT_BASE_PARAMS["group_by"] == "name-date"
    # game_date_gt/lt are deliberately NOT used — probed unreliable (silently season-wide for
    # some seasons); hfMo (passed per-call in fetch_month) is the reliable month filter.
    assert "game_date_gt" not in sc.SAVANT_BASE_PARAMS
    assert "game_date_lt" not in sc.SAVANT_BASE_PARAMS


# ── partitioning matches E7.1's (season, <level-dim>, month) convention ────────

def test_partition_cols():
    assert sc.PARTITION_COLS == ["season", "level", "month"]


def test_table_uri():
    assert sc._table_uri() == "s3://baseball-betting-ml-artifacts/baseball/milb/statcast_aaa"


# ── column rename map: no collisions, dtypes are one of the three supported ────

def test_column_rename_staged_names_are_unique():
    staged = [s for s, _ in sc.COLUMN_RENAME.values()]
    assert len(staged) == len(set(staged)), "duplicate staged column name in COLUMN_RENAME"


def test_column_rename_dtypes_are_valid():
    assert {dtype for _, dtype in sc.COLUMN_RENAME.values()} <= {"str", "Int64", "float64"}


def test_column_rename_covers_identity_and_key_metrics():
    raw_cols = set(sc.COLUMN_RENAME)
    assert {"player_id", "player_name", "game_pk", "game_date"} <= raw_cols
    # E7.3's stated inputs: wOBA, K%, BB%, ISO
    assert {"woba", "k_percent", "bb_percent", "iso"} <= raw_cols


def test_averaged_physical_columns_are_avg_prefixed():
    # Honesty guard: a per-game-average metric must never silently read like a per-pitch value.
    physical_raw = ["launch_speed", "launch_angle", "spin_rate", "bat_speed", "swing_length",
                     "attack_angle", "release_pos_z", "release_pos_x"]
    for raw_col in physical_raw:
        staged, _ = sc.COLUMN_RENAME[raw_col]
        assert staged.startswith("avg_"), f"{raw_col} -> {staged} should be avg_-prefixed"


# ── transform(): rename + cast + identity columns + dup detection ──────────────

def _raw_row(**overrides) -> pd.DataFrame:
    row = {
        "player_id": "672012", "player_name": "Black, Tyler", "game_date": "2024-07-02",
        "game_pk": "752828", "total_pitches": "36", "pitch_percent": "100", "ba": "0.5",
        "iso": "0.75", "babip": "0.333", "slg": "1.25", "woba": "0.718", "xwoba": "0.516",
        "xba": "0.402", "hits": "2", "abs": "4", "launch_speed": "96.2", "launch_angle": "5",
        "spin_rate": "2147", "velocity": "90.7", "effective_speed": "91.44", "whiffs": "0",
        "swings": "17", "takes": "19", "pa": "6", "bip": "4", "singles": "1", "doubles": "0",
        "triples": "0", "hrs": "1", "so": "0", "k_percent": "0", "bb": "2", "bb_percent": "33.3",
        "obp": "0.667", "pitches": "36",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_transform_renames_and_casts():
    df = sc.transform(
        _raw_row(), season=2024, month=7, level="AAA", player_type="batter",
        ingestion_ts="2026-07-25T00:00:00+00:00",
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["player_id"] == 672012 and row["game_pk"] == 752828
    assert row["player_name"] == "Black, Tyler"
    assert row["avg_exit_velocity_mph"] == 96.2       # launch_speed -> avg_-prefixed
    assert row["iso_value"] == 0.75                     # iso -> iso_value (matches MLB naming)
    assert row["plate_appearances"] == 6                # pa -> plate_appearances
    assert row["home_runs"] == 1                         # hrs -> home_runs
    # identity/grain columns
    assert row["level"] == "AAA" and row["player_type"] == "batter"
    assert row["season"] == 2024 and row["month"] == 7
    assert row["ingestion_ts"] == "2026-07-25T00:00:00+00:00"


def test_transform_drops_the_pitches_duplicate_column():
    df = sc.transform(
        _raw_row(), season=2024, month=7, level="AAA", player_type="batter",
        ingestion_ts="2026-07-25T00:00:00+00:00",
    )
    # `pitches` (the leaderboard's leading column) is verified-duplicate of total_pitches and
    # intentionally dropped — no `pitches` column should survive into the staged frame.
    assert "pitches" not in df.columns
    assert df.iloc[0]["total_pitches"] == 36


def test_transform_empty_input_returns_empty():
    df = sc.transform(
        pd.DataFrame(), season=2024, month=7, level="AAA", player_type="batter",
        ingestion_ts="2026-07-25T00:00:00+00:00",
    )
    assert df.empty


def test_transform_warns_but_does_not_crash_on_duplicate_grain_key(caplog):
    raw = pd.concat([_raw_row(), _raw_row()], ignore_index=True)  # exact dup (player,game,type)
    df = sc.transform(
        raw, season=2024, month=7, level="AAA", player_type="batter",
        ingestion_ts="2026-07-25T00:00:00+00:00",
    )
    assert len(df) == 2  # not deduped — just warned


# ── CLI parsers (same shape as ingest_milb_to_s3.py's) ──────────────────────────

def test_parse_seasons_range_and_list():
    assert sc._parse_seasons("2022-2025") == [2022, 2023, 2024, 2025]
    assert sc._parse_seasons("2024") == [2024]
    assert sc._parse_seasons("2022,2024,2026") == [2022, 2024, 2026]


def test_parse_month():
    assert sc._parse_month("2024-06") == (2024, 6)
    assert sc._parse_month(None) is None


def test_iter_months_spans_year_boundary():
    assert list(sc.iter_months((2024, 11), (2025, 2))) == [
        (2024, 11), (2024, 12), (2025, 1), (2025, 2)]
    assert list(sc.iter_months((2024, 6), (2024, 6))) == [(2024, 6)]
