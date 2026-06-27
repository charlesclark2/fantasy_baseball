"""E13.10 TRACK A — the marketable batter-hot-zone × pitcher-tendency OVERLAY.

`build_overlay()` turns the two profiles into the STRUCTURED JSON the frontend renders natively
(the actual product — NO image pipeline). One object per (batter × pitcher, as-of date): a long-
form `cells` list keyed by (cell, pitch_group ∈ {fastball, breaking, offspeed, all}) → batter run
value + pitcher usage frequency + the pitcher's mean location in that cell (the bubble position),
plus the batter's strike-zone bounds, the overlap scalar, and matchup metadata.

`render_overlay_png()` is a RESEARCH PROOF ONLY — it consumes the same JSON to validate the overlay
logic visually. Write it to an S3 artifact path, NOT git and NOT a user-served path. Do NOT build a
per-matchup PNG pipeline; the frontend renders the JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .grid import GridSpec, PITCH_GROUPS
from .overlap import compute_overlap

SCHEMA_VERSION = "2.0"
# Called-zone box (plate 17in + ball ⇒ half-width ≈ 0.83ft; z normalized [0,1]).
ZONE_X_HALF = 0.83
# Public pitch-group names (the JSON contract); internal codes are FB/BR/OS.
GROUP_NAME = {"FB": "fastball", "BR": "breaking", "OS": "offspeed", "ALL": "all"}
DEFAULT_SZ_TOP, DEFAULT_SZ_BOT = 3.4, 1.5


def _dense(rows: pd.DataFrame, value_col: str, grid: GridSpec, fill: float = np.nan):
    """Dense [iz][ix] array of `value_col` from sparse (ix, iz) rows."""
    arr = np.full((grid.nz, grid.nx), fill, float)
    if value_col not in rows.columns:
        return arr
    for r in rows.itertuples():
        arr[int(r.iz), int(r.ix)] = getattr(r, value_col)
    return arr


def _z_ft(z_norm: float, sz_top: float, sz_bot: float) -> float:
    return sz_bot + z_norm * (sz_top - sz_bot)


def build_overlay(batter_val: pd.DataFrame, pitcher_freq: pd.DataFrame, *,
                  batter_id: int, b_hand: str, pitcher_id: int, p_hand: str,
                  grid: GridSpec, as_of_date: str,
                  batter_name: str | None = None, pitcher_name: str | None = None,
                  sz_top: float | None = None, sz_bot: float | None = None) -> dict:
    """Structured matchup JSON (the deliverable). See module docstring for the contract."""
    sz_top = float(sz_top) if sz_top else DEFAULT_SZ_TOP
    sz_bot = float(sz_bot) if sz_bot else DEFAULT_SZ_BOT
    bsel = batter_val[(batter_val["batter_id"] == batter_id)
                      & (batter_val["vs_p_hand"] == p_hand)]
    psel = pitcher_freq[(pitcher_freq["pitcher_id"] == pitcher_id)
                        & (pitcher_freq["vs_b_hand"] == b_hand)]

    # Dense per-group arrays.
    val, swv, whf, xwo, frq, lx, lz = {}, {}, {}, {}, {}, {}, {}
    for g in PITCH_GROUPS:
        bg, pg = bsel[bsel["pgroup"] == g], psel[psel["pgroup"] == g]
        val[g] = _dense(bg, "value", grid)
        swv[g] = _dense(bg, "swing_value", grid)
        whf[g] = _dense(bg, "whiff_rate", grid)
        xwo[g] = _dense(bg, "xwoba_con", grid)
        frq[g] = _dense(pg, "freq", grid, fill=0.0)
        lx[g] = _dense(pg, "loc_x", grid)
        lz[g] = _dense(pg, "loc_znorm", grid)

    # ALL: usage-weighted batter value + total location density + usage-weighted location/whiff/xwoba.
    freq_all = np.nansum([np.nan_to_num(frq[g]) for g in PITCH_GROUPS], axis=0)
    def _wavg(maps):
        num = np.nansum([np.nan_to_num(maps[g]) * np.nan_to_num(frq[g]) for g in PITCH_GROUPS], axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(freq_all > 0, num / freq_all, np.nan)
    val["ALL"], swv["ALL"], whf["ALL"], xwo["ALL"] = _wavg(val), _wavg(swv), _wavg(whf), _wavg(xwo)
    frq["ALL"] = freq_all
    lx["ALL"], lz["ALL"] = _wavg(lx), _wavg(lz)

    cells = []
    for g in list(PITCH_GROUPS) + ["ALL"]:
        for iz in range(grid.nz):
            for ix in range(grid.nx):
                cx, cz = grid.cell_center(ix, iz)
                loc_x = lx[g][iz, ix]
                loc_zn = lz[g][iz, ix]
                px = float(loc_x) if np.isfinite(loc_x) else round(cx, 4)
                pzn = float(loc_zn) if np.isfinite(loc_zn) else cz
                cells.append({
                    "pitch_group": GROUP_NAME[g], "ix": ix, "iz": iz,
                    "x_ft": round(cx, 4), "z_norm": round(cz, 4),
                    "z_ft": round(_z_ft(cz, sz_top, sz_bot), 4),
                    # swing_value = delta_run_exp conditioned on swings (excludes called balls/strikes).
                    # This is what drives the cell color — red=batter handles swings well, blue=struggles.
                    "batter_run_value": _num(swv[g][iz, ix]),
                    "batter_whiff": _num(whf[g][iz, ix]),
                    "batter_xwoba": _num(xwo[g][iz, ix]),
                    "pitcher_usage_freq": _num(frq[g][iz, ix], 5),
                    "pitcher_loc": {"x_ft": round(px, 4),
                                    "z_ft": round(_z_ft(pzn, sz_top, sz_bot), 4)},
                })

    pairs = pd.DataFrame([dict(batter_id=batter_id, b_hand=b_hand,
                               pitcher_id=pitcher_id, p_hand=p_hand)])
    ov = compute_overlap(batter_val, pitcher_freq, pairs)
    overlap_scalar = _num(ov.loc[0, "overlap"], 6)
    b_cold = bool(bsel["is_cold_start"].any()) if not bsel.empty else True
    p_cold = bool(psel["is_cold_start"].any()) if not psel.empty else True

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": as_of_date,
        "matchup": {
            "batter_id": int(batter_id), "batter_name": batter_name, "b_hand": b_hand,
            "pitcher_id": int(pitcher_id), "pitcher_name": pitcher_name, "p_hand": p_hand,
        },
        "strike_zone": {"sz_top": round(sz_top, 4), "sz_bot": round(sz_bot, 4)},
        "grid": {
            "nx": grid.nx, "nz": grid.nz,
            "x_edges": [round(grid.x_min + i * grid.x_step, 4) for i in range(grid.nx + 1)],
            "z_norm_edges": [round(grid.z_min + i * grid.z_step, 4) for i in range(grid.nz + 1)],
            "orientation": "cells carry (ix, iz); iz=0 is bottom of zone, ix=0 is catcher-POV left",
            "x_units": "feet (catcher POV)",
            "z_units": "normalized strike-zone height (0=bottom, 1=top); z_ft via strike_zone bounds",
            "called_zone": {"x_half_ft": ZONE_X_HALF, "z_norm": [0.0, 1.0]},
        },
        "pitch_groups": ["fastball", "breaking", "offspeed", "all"],
        "overlap_scalar": overlap_scalar,
        "overlap_units": "expected batter run value per pitch, weighted by pitcher usage (>0 favors batter)",
        "is_cold_start": {"batter": b_cold, "pitcher": p_cold},
        "cells": cells,
    }


def _num(v, nd: int = 4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), nd)


def _cells_to_grid(overlay: dict, group: str, field: str):
    """Reconstruct a dense [iz][ix] array of `field` for one pitch_group from the cells list."""
    g = overlay["grid"]
    arr = np.full((g["nz"], g["nx"]), np.nan, float)
    for c in overlay["cells"]:
        if c["pitch_group"] != group:
            continue
        v = c[field]
        arr[c["iz"], c["ix"]] = np.nan if v is None else v
    return arr


def render_overlay_png(overlay: dict, out_path: str | Path) -> Path:
    """RESEARCH PROOF ONLY (write to S3 artifact path, not git/not user-served): consumes the same
    JSON and draws, per group + an ALL panel, the batter run-value HEAT (diverging, red=hot) with
    the pitcher's usage as proportional BUBBLES at the measured location. Validates the overlay
    logic visually; the frontend renders the JSON natively. Requires matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = overlay["grid"]
    xe, ze = g["x_edges"], g["z_norm_edges"]
    extent = [xe[0], xe[-1], ze[0], ze[-1]]
    sz = overlay["strike_zone"]
    panels = ["fastball", "breaking", "offspeed", "all"]
    m = overlay["matchup"]

    def _zn(z_ft):  # map a location's z_ft back to normalized for plotting
        return (z_ft - sz["sz_bot"]) / max(1e-6, sz["sz_top"] - sz["sz_bot"])

    allval = np.concatenate([_cells_to_grid(overlay, k, "batter_run_value").ravel() for k in panels])
    vmax = max(0.02, float(np.nanpercentile(np.abs(allval), 95)) if np.isfinite(allval).any() else 0.05)
    maxfreq = max(1e-9, max(float(np.nanmax(np.nan_to_num(_cells_to_grid(overlay, k, "pitcher_usage_freq"))))
                            for k in panels))

    fig, axes = plt.subplots(1, 4, figsize=(19, 5.0), constrained_layout=True)
    im = None
    for ax, key in zip(axes, panels):
        val = _cells_to_grid(overlay, key, "batter_run_value")
        im = ax.imshow(val, origin="lower", extent=extent, aspect="auto",
                       cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        xs, zs, ss = [], [], []
        for c in overlay["cells"]:
            if c["pitch_group"] != key:
                continue
            f = c["pitcher_usage_freq"] or 0.0
            if f > 0:
                xs.append(c["pitcher_loc"]["x_ft"]); zs.append(_zn(c["pitcher_loc"]["z_ft"]))
                ss.append(900.0 * f / maxfreq)
        if xs:
            ax.scatter(xs, zs, s=ss, facecolors="none", edgecolors="black",
                       linewidths=1.3, alpha=0.8)
        ax.add_patch(plt.Rectangle((-ZONE_X_HALF, 0.0), 2 * ZONE_X_HALF, 1.0, fill=False,
                                   edgecolor="k", lw=1.8))
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_title(key.capitalize(), fontsize=12)
        ax.set_xlabel("plate_x (ft, catcher POV)")
        ax.set_xticks([-1, 0, 1])
        if key == "fastball":
            ax.set_ylabel("zone height (0=bottom, 1=top)")
    fig.colorbar(im, ax=axes, shrink=0.75,
                 label="batter run value / pitch  (red = batter hot)")

    ov = overlay.get("overlap_scalar")
    cold = overlay["is_cold_start"]
    bn = m.get("batter_name") or m["batter_id"]
    pn = m.get("pitcher_name") or m["pitcher_id"]
    sup = f"{bn} ({m['b_hand']}HB)  vs  {pn} ({m['p_hand']}HP)"
    sup += f"      overlap = {ov:+.4f}" if ov is not None else "      overlap = n/a"
    if cold["batter"] or cold["pitcher"]:
        sup += f"   [cold-start: batter={cold['batter']}, pitcher={cold['pitcher']}]"
    sup += f"      as-of {overlay['as_of_date']}    (PROOF — bubbles = pitcher usage/location)"
    fig.suptitle(sup, fontsize=13)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=115)
    plt.close(fig)
    return out_path


def write_overlay_json(overlay: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(overlay, indent=2))
    return out_path
