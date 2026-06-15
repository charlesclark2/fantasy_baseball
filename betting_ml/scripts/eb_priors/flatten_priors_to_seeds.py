"""
flatten_priors_to_seeds.py — Story A2.11 Task 1: materialize the EB priors as
dbt seeds so the posterior dbt models can `ref` them.

The priors live as per-season JSON in betting_ml/models/eb_priors/, produced by
the fit_*_priors.py scripts. dbt cannot read filesystem JSON, so this flattens
them into version-controlled CSVs under dbt/seeds/ (one row per
(season, metric, band/role/cluster)). `dbtf seed` then lands them in Snowflake.

`band_rank` encodes the Python band-fallback order (_get_prior_cell): when a
game's exact experience band has no prior cell, the posterior model falls back
to the LOWEST-rank band present for that (season, metric). Only NON-NULL cells
are emitted (null cells are exactly the ones the fallback skips).

Re-run this whenever fit_*_priors.py regenerates the JSON. Fast (local file IO
only — no Snowflake). After running, `dbtf seed --select ref_eb_starter_priors`.

Usage:
    uv run python betting_ml/scripts/eb_priors/flatten_priors_to_seeds.py
    uv run python betting_ml/scripts/eb_priors/flatten_priors_to_seeds.py --family starter
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PRIORS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors"
_SEEDS_DIR = _PROJECT_ROOT / "dbt" / "seeds"

# Experience-band fallback order — must match fit_starter_priors.py / the
# _get_prior_cell scan order in compute_starter_posteriors.py.
_STARTER_BAND_RANK = {"u25": 0, "a25": 1, "a30": 2, "a33": 3}


def _flatten_starter() -> tuple[str, list[str], list[list]]:
    """starter_priors_{season}.json → rows of
    (season, metric, age_band, band_rank, mu, sigma, n_starters)."""
    rows: list[list] = []
    for path in sorted(_PRIORS_DIR.glob("starter_priors_*.json")):
        doc = json.loads(path.read_text())
        season = int(doc["season"])
        for metric, bands in doc["priors"].items():
            for band, cell in bands.items():
                if not cell:  # null cell — the fallback skips these
                    continue
                rows.append([
                    season,
                    metric,
                    band,
                    _STARTER_BAND_RANK.get(band, 99),
                    round(float(cell["mu"]), 6),
                    round(float(cell["sigma"]), 6),
                    int(cell.get("n_starters", 0) or 0),
                ])
    rows.sort(key=lambda r: (r[0], r[1], r[3]))
    header = ["season", "metric", "age_band", "band_rank", "mu", "sigma", "n_starters"]
    return "ref_eb_starter_priors", header, rows


def _flatten_lineup() -> tuple[str, list[str], list[list]]:
    """lineup_priors_{season}.json → rows of
    (season, metric, role, batter_hand, alpha, beta, mu, sigma).
    Beta metrics (woba/k_pct/bb_pct) carry {alpha,beta}; iso carries {mu,sigma}.
    Hand ∈ {R,L,S}; the posterior model falls back to the R cell for a missing hand
    (mirrors compute_lineup_posteriors._get_prior_cell)."""
    rows: list[list] = []
    for path in sorted(_PRIORS_DIR.glob("lineup_priors_*.json")):
        doc = json.loads(path.read_text())
        season = int(doc["season"])
        for metric, roles in doc["priors"].items():
            for role, hands in roles.items():
                for hand, cell in hands.items():
                    if not cell:
                        continue
                    rows.append([
                        season, metric, role, hand,
                        round(float(cell["alpha"]), 6) if "alpha" in cell else None,
                        round(float(cell["beta"]), 6) if "beta" in cell else None,
                        round(float(cell["mu"]), 6) if "mu" in cell else None,
                        round(float(cell["sigma"]), 6) if "sigma" in cell else None,
                    ])
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    header = ["season", "metric", "role", "batter_hand", "alpha", "beta", "mu", "sigma"]
    return "ref_eb_lineup_priors", header, rows


_BULLPEN_BAND_RANK = {"lt_26": 0, "26_30": 1, "31_34": 2, "gte_35": 3}


def _flatten_bullpen() -> tuple[str, list[str], list[list]]:
    """bullpen_priors_{season}.json → rows of
    (season, metric, role, age_band, band_rank, mu, sigma, n_relievers).
    band_rank encodes the age-band fallback order (compute_bullpen._get_prior_cell:
    lt_26<26_30<31_34<gte_35). Roles: closer_tier/high_leverage/low_leverage/no_prior_season."""
    rows: list[list] = []
    for path in sorted(_PRIORS_DIR.glob("bullpen_priors_*.json")):
        doc = json.loads(path.read_text())
        season = int(doc["season"])
        for metric, roles in doc["priors"].items():
            for role, bands in roles.items():
                for band, cell in bands.items():
                    if not cell:
                        continue
                    rows.append([
                        season, metric, role, band,
                        _BULLPEN_BAND_RANK.get(band, 99),
                        round(float(cell["mu"]), 6),
                        round(float(cell["sigma"]), 6),
                        int(cell.get("n_relievers", 0) or 0),
                    ])
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[4]))
    header = ["season", "metric", "role", "age_band", "band_rank", "mu", "sigma", "n_relievers"]
    return "ref_eb_bullpen_priors", header, rows


_FAMILIES = {
    "starter": _flatten_starter,
    "lineup":  _flatten_lineup,
    "bullpen": _flatten_bullpen,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=sorted(_FAMILIES) + ["all"], default="all")
    args = ap.parse_args()

    families = _FAMILIES if args.family == "all" else {args.family: _FAMILIES[args.family]}
    for fam, fn in families.items():
        name, header, rows = fn()
        out = _SEEDS_DIR / f"{name}.csv"
        with out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        seasons = sorted({r[0] for r in rows})
        print(f"[{fam}] wrote {len(rows)} rows → {out.relative_to(_PROJECT_ROOT)} "
              f"(seasons {seasons[0]}–{seasons[-1]})")


if __name__ == "__main__":
    main()
