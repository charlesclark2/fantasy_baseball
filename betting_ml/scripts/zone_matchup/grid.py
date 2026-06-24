"""E13.10 zone grid + pitch-type grouping — PURE logic (no duckdb/S3; unit-tested).

The strike-zone is discretized into an NX×NZ grid in (plate_x_ft, z_norm) space, where
  z_norm = (plate_z_ft - strike_zone_bot_ft) / (strike_zone_top_ft - strike_zone_bot_ft)
so z_norm ∈ [0, 1] is the per-batter rulebook zone (height-normalized — a 6'5" and a 5'9"
hitter share the same coordinate). x stays in feet (home plate is 17in ≈ 1.42ft wide, so the
rulebook zone half-width incl. the ball radius is ≈ 0.83ft). The grid covers the zone PLUS a
shadow band so chase/edge cells exist.

Bins are UNIFORM, so the same closed-form `clamp(floor((v-min)/step), 0, N-1)` is used in both
Python (here) and the duckdb SQL (lakehouse.py) — the two MUST agree, which the grid unit tests
pin. Pitches outside the grid clamp to the edge cell (a wild pitch still counts as "way outside").
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Grid geometry (defaults; overridable via GridSpec) ────────────────────────
GRID_NX = 5
GRID_NZ = 5
X_MIN, X_MAX = -1.4, 1.4        # feet, catcher's POV (− = inside to a RHB / 3B side)
Z_MIN, Z_MAX = -0.25, 1.25      # normalized strike-zone units (0 = bottom of zone, 1 = top)

# ── Pitch-type → arsenal group (keeps per-cell counts from going too sparse) ──
# Statcast pitch_type codes observed in the lakehouse: FF SI FC FA FT (fastball),
# SL CU ST SV KC CS SC KN (breaking), CH FS FO EP (offspeed). Unknown/None → dropped upstream.
_FASTBALL = {"FF", "SI", "FC", "FA", "FT", "SF"}
_BREAKING = {"SL", "CU", "ST", "SV", "KC", "CS", "SC", "KN", "ST"}
_OFFSPEED = {"CH", "FS", "FO", "EP"}

PITCH_GROUPS = ("FB", "BR", "OS")
PITCH_GROUP_LABEL = {"FB": "Fastballs", "BR": "Breaking", "OS": "Offspeed"}


@dataclass(frozen=True)
class GridSpec:
    nx: int = GRID_NX
    nz: int = GRID_NZ
    x_min: float = X_MIN
    x_max: float = X_MAX
    z_min: float = Z_MIN
    z_max: float = Z_MAX

    @property
    def x_step(self) -> float:
        return (self.x_max - self.x_min) / self.nx

    @property
    def z_step(self) -> float:
        return (self.z_max - self.z_min) / self.nz

    @property
    def n_cells(self) -> int:
        return self.nx * self.nz

    def bin_x(self, plate_x_ft: float) -> int:
        ix = int((plate_x_ft - self.x_min) // self.x_step)
        return max(0, min(self.nx - 1, ix))

    def bin_z(self, z_norm: float) -> int:
        iz = int((z_norm - self.z_min) // self.z_step)
        return max(0, min(self.nz - 1, iz))

    def cell_center(self, ix: int, iz: int) -> tuple[float, float]:
        """(x_ft, z_norm) center of cell (ix, iz)."""
        cx = self.x_min + (ix + 0.5) * self.x_step
        cz = self.z_min + (iz + 0.5) * self.z_step
        return cx, cz

    def cell_center_z_ft(self, iz: int, sz_bot: float = 1.5, sz_top: float = 3.4) -> float:
        """z_norm cell center mapped back to feet using a nominal strike zone (render convenience)."""
        _, cz = self.cell_center(0, iz)
        return sz_bot + cz * (sz_top - sz_bot)

    def sql_ix(self, x_col: str) -> str:
        """duckdb expression for the x-bin of `x_col` — MUST match bin_x()."""
        return (f"greatest(0, least({self.nx - 1}, "
                f"floor(({x_col} - ({self.x_min})) / {self.x_step})::int))")

    def sql_iz(self, znorm_expr: str) -> str:
        """duckdb expression for the z-bin of `znorm_expr` — MUST match bin_z()."""
        return (f"greatest(0, least({self.nz - 1}, "
                f"floor(({znorm_expr} - ({self.z_min})) / {self.z_step})::int))")


def cell_key(ix: int, iz: int) -> str:
    return f"{ix}_{iz}"


def group_of(pitch_type: str | None) -> str | None:
    """Map a Statcast pitch_type to an arsenal group, or None if unclassifiable (drop upstream)."""
    if not pitch_type:
        return None
    pt = pitch_type.upper()
    if pt in _FASTBALL:
        return "FB"
    if pt in _BREAKING:
        return "BR"
    if pt in _OFFSPEED:
        return "OS"
    return None


def sql_group_case(pitch_type_col: str) -> str:
    """duckdb CASE mapping pitch_type → arsenal group — MUST match group_of()."""
    fb = ", ".join(f"'{c}'" for c in sorted(_FASTBALL))
    br = ", ".join(f"'{c}'" for c in sorted(_BREAKING))
    os = ", ".join(f"'{c}'" for c in sorted(_OFFSPEED))
    return (f"CASE WHEN {pitch_type_col} IN ({fb}) THEN 'FB' "
            f"WHEN {pitch_type_col} IN ({br}) THEN 'BR' "
            f"WHEN {pitch_type_col} IN ({os}) THEN 'OS' ELSE NULL END")


# ── pitch_description → swing / whiff semantics (matches the lakehouse values) ─
SWING_DESCRIPTIONS = (
    "hit_into_play", "foul", "foul_tip", "swinging_strike", "swinging_strike_blocked",
    "foul_bunt", "missed_bunt", "foul_pitchout", "swinging_pitchout",
)
WHIFF_DESCRIPTIONS = ("swinging_strike", "swinging_strike_blocked", "missed_bunt", "swinging_pitchout")


def sql_in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"
