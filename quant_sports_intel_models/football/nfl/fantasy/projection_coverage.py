"""projection_coverage.py — NF-D11: the STANDING projection-universe coverage diagnostic.

⭐ WHY THIS IS A PERMANENT CHECK, NOT A ONE-OFF SCRIPT. The market's ADP list is a free, independent
census of "players a human is actually being asked to draft." Diffing it against the projection's own
(name, position) set is therefore the cheapest possible audit of our UNIVERSE — and in the NF3 build
(2026-07-29) this single diff caught TWO different classes of bug at once:

  1. a NAME-ALIAS JOIN BUG — FFC's "Kenny Gainwell" vs nflverse's "KENNETH GAINWELL" silently cost a
     genuinely draftable RB (18 g / 221 PPR) his ADP on all 8 samples; and
  2. a MODEL/UNIVERSE GAP — Brandon Aiyuk, Tank Dell, Jonathon Brooks and MarShawn Lloyd had NO
     projection row at all, because the base-season inner-join anchor deleted every player who missed
     the whole base season (NF-D11's root cause).

Those two look IDENTICAL from the outside (an ADP name with no board row), which is exactly why the
audit indexes the projection by SURNAME as well: a surname that IS present at the same position means
the player is in our universe under a different spelling ⇒ `alias_candidate` (fix the alias map); a
surname that is absent entirely means he is genuinely NOT in the projection ⇒ `true_absence` (a model
/ universe gap — the expensive kind). Reporting them in one undifferentiated pile is what let the
model gap hide behind the alias noise for a whole build.

Pure + IO-free (pandas in, dict out) so the fast gate covers it; `run_season_projection` calls it at
the end of every board build (WARN-tier — a coverage gap is loud, never fatal) and lands the result in
the run summary + the report, so a future universe regression surfaces on the very next run.
"""
from __future__ import annotations

import logging

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as _ADP

log = logging.getLogger("nfl.fantasy.coverage")

# The positions the projection product covers. An ADP row outside this set (K/DEF) is not a gap.
_COVERED_POSITIONS = ("QB", "RB", "WR", "TE", "FB")

# An unmatched name this far down the draft board is a deep-bench flyer, not a universe defect; the
# audit still lists it, but the ALERT threshold keys off the draftable range so the check stays
# actionable instead of crying wolf on the 200th pick.
_ACTIONABLE_ADP = 180.0


def _surname(normalized: str) -> str:
    parts = (normalized or "").split()
    return parts[-1] if parts else ""


def audit_adp_coverage(
    adp: pd.DataFrame,
    proj: pd.DataFrame,
    name_col: str = "player_name",
    pos_col: str = "position",
    actionable_adp: float = _ACTIONABLE_ADP,
) -> dict:
    """Diff a market ADP sample against the projection's own (name, position) universe.

    Both sides are normalized through `adp_source._normalize_name` (the SAME vetted normalizer the
    real ADP join uses — so an alias the map already fixes is not re-reported as a miss). Each
    unmatched ADP row is then classified:

      • `alias_candidate` — the SURNAME exists in the projection at that position ⇒ our universe
        very likely HAS this player under a different first name/spelling. Fix = an
        `adp_source._NAME_ALIASES` entry (cheap), and the candidate matches are listed.
      • `true_absence`    — no surname match at that position ⇒ the player is genuinely NOT in the
        projection. Fix = a MODEL/universe change (NF-D11's class), not a string map.

    Returns a JSON-able dict: match rate, the two unmatched buckets (each sorted by ADP, so the most
    draftable gap is first), and the actionable counts the caller alerts on."""
    out = {
        "n_adp_rows": int(len(adp)) if adp is not None else 0,
        "n_adp_covered_positions": 0,
        "n_matched": 0,
        "pct_matched": None,
        "n_alias_candidates": 0,
        "n_true_absences": 0,
        "n_actionable_true_absences": 0,
        "alias_candidates": [],
        "true_absences": [],
    }
    if adp is None or len(adp) == 0 or proj is None or len(proj) == 0:
        return out

    p = proj.copy()
    p["_n"] = [_ADP._normalize_name(v) for v in p[name_col]]
    p["_pos"] = p[pos_col].astype("string").str.upper()
    by_name_pos = set(zip(p["_n"], p["_pos"]))
    by_surname_pos: dict[tuple[str, str], list[str]] = {}
    for n, pos in zip(p["_n"], p["_pos"]):
        by_surname_pos.setdefault((_surname(n), pos), []).append(n)

    a = adp.copy()
    a["_pos"] = a[pos_col].astype("string").str.upper()
    a = a[a["_pos"].isin(_COVERED_POSITIONS)]
    out["n_adp_covered_positions"] = int(len(a))
    if a.empty:
        return out
    a["_n"] = [_ADP._normalize_name(v) for v in a[name_col]]
    a["_adp"] = pd.to_numeric(a.get("adp"), errors="coerce")

    matched = 0
    for _, r in a.sort_values("_adp", na_position="last").iterrows():
        key = (r["_n"], r["_pos"])
        if key in by_name_pos:
            matched += 1
            continue
        cands = by_surname_pos.get((_surname(r["_n"]), r["_pos"]), [])
        rec = {"adp_name": r[name_col], "position": r["_pos"],
               "adp": None if pd.isna(r["_adp"]) else float(r["_adp"])}
        if cands:
            rec["projection_surname_matches"] = sorted(set(cands))
            out["alias_candidates"].append(rec)
        else:
            out["true_absences"].append(rec)

    out["n_matched"] = int(matched)
    out["pct_matched"] = round(100.0 * matched / max(1, len(a)), 1)
    out["n_alias_candidates"] = len(out["alias_candidates"])
    out["n_true_absences"] = len(out["true_absences"])
    out["n_actionable_true_absences"] = sum(
        1 for r in out["true_absences"] if r["adp"] is not None and r["adp"] <= actionable_adp)
    return out


def merge_sample_audits(by_sample: dict[str, dict]) -> dict:
    """Roll several per-(format, size) audits into one verdict.

    ⭐ AUDIT EVERY SAMPLE, NOT ONE BOARD (the NF3 lesson): ADP is format-specific — Josh Allen is
    ADP 28.1 in PPR and 1.5 in superflex — so a player can be undrafted in one sample and a
    first-rounder in another. A gap that shows up in ONLY the superflex sample is still a gap, and
    auditing a single board would miss it. The union of the per-sample findings is the universe
    verdict; the per-sample detail says where it bites."""
    union_abs: dict[tuple[str, str], dict] = {}
    union_alias: dict[tuple[str, str], dict] = {}
    for sample, a in (by_sample or {}).items():
        for r in a.get("true_absences", []):
            k = (r["adp_name"], r["position"])
            cur = union_abs.setdefault(k, {**r, "samples": [], "best_adp": r["adp"]})
            cur["samples"].append(sample)
            if r["adp"] is not None and (cur["best_adp"] is None or r["adp"] < cur["best_adp"]):
                cur["best_adp"] = r["adp"]
        for r in a.get("alias_candidates", []):
            k = (r["adp_name"], r["position"])
            cur = union_alias.setdefault(k, {**r, "samples": []})
            cur["samples"].append(sample)
    absences = sorted(union_abs.values(),
                      key=lambda r: (r["best_adp"] is None, r["best_adp"] if r["best_adp"] is not None else 0))
    aliases = sorted(union_alias.values(), key=lambda r: r["adp_name"])
    pcts = [a.get("pct_matched") for a in (by_sample or {}).values() if a.get("pct_matched") is not None]
    return {
        "n_samples": len(by_sample or {}),
        "pct_matched_min": round(min(pcts), 1) if pcts else None,
        "pct_matched_mean": round(float(sum(pcts) / len(pcts)), 1) if pcts else None,
        "n_true_absences": len(absences),
        "n_alias_candidates": len(aliases),
        "n_actionable_true_absences": sum(
            1 for r in absences if r["best_adp"] is not None and r["best_adp"] <= _ACTIONABLE_ADP),
        "true_absences": absences,
        "alias_candidates": aliases,
        "by_sample": {k: {kk: vv for kk, vv in v.items()
                          if kk not in ("true_absences", "alias_candidates")}
                      for k, v in (by_sample or {}).items()},
    }


def log_adp_coverage(audit: dict, label: str = "") -> None:
    """WARN-tier reporting of an `audit_adp_coverage` result. An ALIAS candidate and a TRUE absence
    are logged SEPARATELY and named, because they route to different fixes (a `_NAME_ALIASES` entry
    vs a model/universe change) — the NF3 build lost a whole cycle to seeing them as one pile."""
    tag = f"[{label}] " if label else ""
    if "by_sample" in audit:      # a merged multi-sample audit
        log.info("%sADP coverage across %d samples: min %.1f%% / mean %.1f%% matched · "
                 "%d alias candidate(s) · %d universe absence(s)", tag, audit.get("n_samples", 0),
                 audit.get("pct_matched_min") or 0.0, audit.get("pct_matched_mean") or 0.0,
                 audit.get("n_alias_candidates", 0), audit.get("n_true_absences", 0))
    else:
        log.info("%sADP coverage: %d/%d matched (%.1f%%)", tag, audit.get("n_matched", 0),
                 audit.get("n_adp_covered_positions", 0), audit.get("pct_matched") or 0.0)
    for r in audit.get("alias_candidates", []):
        log.warning("%sADP name unmatched but SURNAME present at %s — likely a NAME-ALIAS miss: "
                    "'%s' (adp %s) ~ %s → add an adp_source._NAME_ALIASES entry",
                    tag, r["position"], r["adp_name"], r["adp"], r.get("projection_surname_matches"))
    for r in audit.get("true_absences", []):
        log.warning("%sADP player ABSENT from the projection universe: '%s' %s (adp %s) — a MODEL "
                    "gap, not a name map (NF-D11 class: audit the player spine)",
                    tag, r["adp_name"], r["position"], r["adp"])
