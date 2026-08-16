"""veteran_level_policy.py — the ONE place the served VETERAN season-projection LEVEL recalibration
is decided (NF-TR2 / NF-TR2b), read by `run_season_projection.build_projection` and stamped onto
every board row. The rookie leg has `rookie_publish_policy`; this is its veteran sibling.

WHAT IS SERVED (when `SERVING_ENABLED`): the NF-TR2b winner — a per-position MULTIPLICATIVE constant
on the per-game RATE, `k_q = Σ realized / Σ projected` over the incumbent-anchored draftable tier of
the trailing `WINDOW_SEASONS` target seasons strictly before the projection season, fitted at BUILD
time from the veteran band panel (walk-forward by construction — a backtest board for season Y is
fitted on < Y, the E5.9 boundary). The correction is carried onto the whole stat line (every scoring
format moves consistently), `proj_games` is untouched (the availability discount stays), the
within-position order is preserved exactly (a positive constant is a monotone map), and the
NF1.9-validated band is left BYTE-IDENTICAL: `attach_season_interval` queries the band model at the
INCUMBENT-EQUIVALENT point (`season_level_recalibration.invert_level`) and brackets it to the served
point. ⛔ The rookie leg is untouched (NF-D21 CLOSED; inherited).

WHY THIS FORM AND NOT THE OTHERS — the record: `ablation_results/nf_tr2_level_recalibration.md`
(NF-TR2, the full-history mean-match: passed every inherited gate, REFUSED by its own no-inflation
level gate — it over-corrects out of fold because the level is non-stationary) and
`ablation_results/nf_tr2_level_recalibration_b.md` (NF-TR2b, the trailing-window successor
declared before its run: CRPS 49.34 vs 49.92 over 13 folds, PBO 0.0, DSR 0.9995 on the declared
3-trial field / 0.999 under NF-B3's field, p 0.0002; pooled OOF tier bias −12.85 → +1.41, every
position within its allowance; the affine foil wins raw CRPS but is refused by C1 — a negative fitted
slope on 6 folds inverts a position's board, the NF-D16 hazard measured; every two-sided anchor
behaves; the CRPS-optimal λ (1.25) sits within noise of the level target (1.0), so the metric and
the constraint do not oppose).

⭐ THE FLIP IS ONE READ OF `serving_form()`. `SERVING_ENABLED = False` returns "" and the board is
BYTE-IDENTICAL to the pre-NF-TR2 incumbent (pinned by test) — the rollback is the same code path.
`assert_coherent()` runs at import and refuses a flip that contradicts the recorded disposition.
"""
from __future__ import annotations

#: The story that selected the served correction, and the one that measured the refused predecessor.
SOURCE_MODEL = "NF-TR2b"
PREDECESSOR = "NF-TR2"
DECISION_STORY = "NF-TR2"
MODEL_VERSION = "nfl_fantasy_nf_tr2b_veteran_level_v1"

#: The recorded disposition of the SOURCE_MODEL's pre-registered gate.
DISPOSITION = "SHIP"                     # NF-TR2b: every gate green (see the module docstring)
PREDECESSOR_DISPOSITION = "CONSTRAINT_REFUSED"   # NF-TR2: refused by its own level gate (L1–L3)

#: The served form + estimator + window — READ from the pre-registration so they cannot drift.
FORM = "pos_const"
ESTIMATOR = "mean_match"
WINDOW_SEASONS = 5                        # == season_level_recalibration.WINDOW_SEASONS (pinned by test)
SELECTION_STATUS = "STATISTICALLY_SELECTED"
STATISTICALLY_SELECTED = True
RECALIBRATED_POSITIONS = ("QB", "RB", "WR", "TE")

#: ⭐ THE FLIP. True ⇒ `build_projection` fits + applies the correction. False ⇒ the identity map,
#: byte-for-byte the pre-NF-TR2 board. Merging this file with True does NOT serve anything by itself:
#: the board is rebuilt + published by the operator (the NF-FRESH2 laptop loop / publish job), and
#: the governance registry's `level_model_version` must be staged/promoted to MODEL_VERSION first —
#: the artifact-stamp gate refuses a mismatch by design.
SERVING_ENABLED: bool = True


def serving_form() -> str:
    """The form to apply at build time, or "" (the identity) when serving is off."""
    return FORM if SERVING_ENABLED else ""


def stamp() -> dict:
    """The board-wide stamp columns (see `run_season_projection.OUTPUT_COLS`)."""
    on = bool(SERVING_ENABLED)
    return {
        "veteran_level_status": ("recalibrated" if on else "incumbent"),
        "veteran_level_form": (FORM if on else ""),
        "veteran_level_window": (int(WINDOW_SEASONS) if on else 0),
        "veteran_level_source_model": (SOURCE_MODEL if on else ""),
        "veteran_level_decision_story": (DECISION_STORY if on else ""),
        "veteran_level_statistically_selected": (bool(STATISTICALLY_SELECTED) if on else False),
        "level_model_version": (MODEL_VERSION if on else "nfl_fantasy_fastpath_v1"),
    }


def assert_coherent() -> None:
    """Refuse a flip that contradicts the recorded disposition (the `rookie_publish_policy` shape)."""
    if SERVING_ENABLED and DISPOSITION != "SHIP":
        raise RuntimeError(
            "veteran_level_policy is INCOHERENT: SERVING_ENABLED=True while DISPOSITION is "
            f"{DISPOSITION!r} — a level correction serves only when its pre-registered gate SHIPPED.")
    if FORM not in ("pos_const", "pos_affine"):
        raise RuntimeError(f"veteran_level_policy: unknown FORM {FORM!r}")


assert_coherent()
