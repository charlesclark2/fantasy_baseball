"""ncaaf_val3b_serve_parity.py — NCAAF-VAL3b §8: can the cleared correction actually SERVE?

The spec gates a pre-opener ship on an **S1-serve-class train/serve parity check against the SERVED
ARTIFACT CONTRACT**, *checked directly — no pace-style ship-vs-serve gap; don't assume*. This module
is that check, and it answers by READING THE ARTIFACTS AND THE SERVING CODE, never from memory.

⭐ **Why a parity check is a separate module rather than a paragraph.** E7.9 named the failure:
a σ fitted on one config served against a μ from another. NF-C0e named the sibling: a term DECLARED
in a contract that nothing ever COMPUTES. Both are invisible to CI (which mocks IO) and to a green
bake-off (which scores the model it built, not the artifact that serves). The only way to know is to
open the served artifact and ask whether the validated quantity can be expressed in it.

Three legs, registered FORWARD in §8 of the pre-registration. **Any leg failing ⇒ DEPLOY-HELD.**

  (i)   EXPRESSIBILITY — can the served mean contract express a WEEK-CONDITIONAL shift at all?
  (ii)  QUANTITY       — is the number that would serve the SAME number this study validated?
  (iii) WEEK COLUMN    — does the serving path carry `season_order_week`, or CFBD's postseason-
                         restarted `week` (the P1.1 leak)?

⛔ This module writes NO served artifact, edits no registry and changes nothing. It reports.

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val3b_serve_parity
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path
from typing import Any

from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models import ncaaf_game_mean as GM
from quant_sports_intel_models.football.ncaaf.models import ncaaf_game_predictor as GP
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3b_single_contrast as V3B

_STORY = "NCAAF-VAL3b/parity"
_RESULTS = Path(B._RESULTS_DIR)
_OUT_JSON = _RESULTS / "ncaaf_val3b_serve_parity.json"
_MODELS = Path(__file__).resolve().parent
_SNAPSHOT_PY = _MODELS / "game_prediction_snapshot.py"

#: The study's cell boundary. A serving implementation reading a DIFFERENT week column applies the
#: correction to different rows — which is the whole of leg (iii).
STUDY_WEEK_COL = V3B.WEEK_COL


def leg_i_expressibility() -> dict[str, Any]:
    """(i) Can `ncaaf_game_mean_v2.json` express `μ − δ·1[week ≤ 3]`?

    Read off the DATACLASS FIELD SET and the `predict` SIGNATURE, not off a docstring: a field that
    does not exist cannot be populated, and a `predict` that never receives a week cannot condition
    on one (the NF-C0e wired-vs-invoked distinction, on the contract side)."""
    fields = set(GM.NcaafGameMeanParams.__dataclass_fields__)
    shift_fields = sorted(f for f in fields
                          if any(t in f.lower() for t in ("shift", "week", "cold", "offset")))
    sig = list(ast.parse(Path(GM.__file__).read_text()).body)
    predict_args: list[str] = []
    for node in ast.walk(ast.parse(Path(GM.__file__).read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == "predict":
            predict_args = [a.arg for a in node.args.args]
    ok = bool(shift_fields) and any("week" in a.lower() for a in predict_args)
    return {
        "leg": "i_expressibility", "ok": ok,
        "artifact": GP.SERVED_MEAN_FILENAME,
        "contract_fields": sorted(fields),
        "week_or_shift_fields": shift_fields,
        "predict_signature": predict_args,
        "finding": (
            "the served mean is a PURE LINEAR COEFFICIENT TABLE — "
            f"{len(fields)} fields, NONE of them a week/shift/cold-start term — and "
            f"`NcaafGameMeanParams.predict{tuple(predict_args)}` receives no week at all. A "
            "week-conditional δ is therefore NOT EXPRESSIBLE in the served contract as it stands; "
            "serving it needs a NEW field (e.g. `cold_start_shift_total` + `cold_start_max_week`) "
            "AND a `predict` that takes the week. That is a contract change with its own schema "
            "bump, not a coefficient refit." if not ok else
            "the served contract carries a week-conditional shift term and `predict` receives a "
            "week, so the validated correction is expressible as-is."),
    }


def leg_ii_quantity() -> dict[str, Any]:
    """(ii) Is the δ that would SERVE the same δ this study VALIDATED?

    The study validated **eight per-fold, in-fold-selected δ's** — each estimated from a nested
    walk-forward inside that fold's own training seasons. The served artifact is a **single
    full-history refit**. So the number that would ship is a NINTH δ, estimated on all 11 seasons,
    which appears in no fold of this study. That is precisely E7.9's train/serve-consistency
    question, and it is a genuine gap even though every per-fold δ is honest.
    """
    d = json.loads((_RESULTS / "ncaaf_val3b_single_contrast.json").read_text())
    deltas = [float(x) for x in d["arm"]["per_fold_delta"]]
    mean_path = Path(GP._ARTIFACT_DIR) / GP.SERVED_MEAN_FILENAME
    mean = json.loads(mean_path.read_text())
    return {
        "leg": "ii_quantity", "ok": False,
        "validated_deltas_per_fold": deltas,
        "n_validated_deltas": len(deltas),
        "delta_min": min(deltas), "delta_max": max(deltas),
        "delta_spread_pts": max(deltas) - min(deltas),
        "served_artifact_fit": {"n_train_rows": mean.get("n_train_rows"),
                                "train_seasons": mean.get("train_seasons"),
                                "fit_at": mean.get("fit_at")},
        "finding": (
            f"the study validated {len(deltas)} PER-FOLD in-fold δ's spanning "
            f"{min(deltas):.3f}–{max(deltas):.3f} pts (spread {max(deltas)-min(deltas):.3f}). The "
            f"served mean is ONE full-history refit ({mean.get('n_train_rows')} rows, "
            f"{len(mean.get('train_seasons') or [])} seasons), so the δ that would actually ship is "
            "a NINTH estimate — fitted on all seasons at once — which appears in no fold of this "
            "study and has never been scored out of sample. Every per-fold δ is honest; the SERVED "
            "one is a different quantity (E7.9 train/serve consistency). ⭐ The spread is not "
            "cosmetic: the estimator is deliberately in-fold, so a full-history δ is not the mean "
            "of the eight — it is a new fit whose out-of-sample behaviour this study does not "
            "certify."),
    }


def _week_col_assignments(module_path: Path, col: str) -> list[dict[str, Any]]:
    """Every `frame[col] = <expr>` in a module, with the RHS classified.

    ⭐ An AST read, not a substring one, and this is the whole point of the leg: a `col in source`
    check is satisfied by `df["season_order_week"] = df["week"]` — an ALIAS of exactly the column
    the study forbids — and by a WARNING COMMENT that names it. Both make the guard PASS on the
    defect it exists to catch (the NF1.7 (a) / INC-38 vacuous-guard class). ⚠️ This module's FIRST
    cut did exactly that and returned a FALSE PASS; the AST version is the fix.
    """
    tree = ast.parse(module_path.read_text())
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not (isinstance(tgt, ast.Subscript) and isinstance(tgt.slice, ast.Constant)
                    and tgt.slice.value == col):
                continue
            rhs = ast.unparse(node.value)
            # peel `.astype(...)` / `.to_numpy()` etc. — a cast does not make an alias honest
            base = rhs.split(".astype")[0].split(".to_numpy")[0].strip()
            is_alias = base.endswith('["week"]') or base.endswith("['week']")
            out.append({"line": node.lineno, "rhs": rhs, "is_raw_week_alias": bool(is_alias)})
    return out


def leg_iii_week_column() -> dict[str, Any]:
    """(iii) Does the serving path carry an HONEST `season_order_week`, or a raw-`week` ALIAS?

    ⛔ CFBD restarts `week` at 1 for the postseason (the P1.1 leak / P0.6b landmine). The study's
    cell is `season_order_week ≤ 3`. A serving implementation keyed on a column of that NAME whose
    VALUES are the restarted `week` would apply a cold-start correction to **bowl and playoff
    games** — silently, on the highest-profile slate of the year — and would LOOK correct in review,
    which is worse than the column simply being absent.
    """
    assigns = _week_col_assignments(_SNAPSHOT_PY, STUDY_WEEK_COL)
    aliases = [a for a in assigns if a["is_raw_week_alias"]]
    honest = [a for a in assigns if not a["is_raw_week_alias"]]
    ok = bool(honest) and not aliases
    return {
        "leg": "iii_week_column", "ok": ok,
        "study_week_col": STUDY_WEEK_COL,
        "serving_module": _SNAPSHOT_PY.name,
        "assignments": assigns,
        "n_raw_week_aliases": len(aliases), "n_honest_derivations": len(honest),
        "finding": (
            f"`{_SNAPSHOT_PY.name}` assigns `{STUDY_WEEK_COL}` at line "
            f"{aliases[0]['line']} as `{aliases[0]['rhs']}` — a VERBATIM ALIAS of CFBD's raw "
            "`week`, added (per its own comment) only to satisfy a frame contract and documented as "
            "UNUSED. So the serving frame carries the study's column NAME with the postseason-"
            "RESTARTED values, and an implementation keyed on that name would apply the cold-start "
            "correction to bowl and playoff games while looking correct in review. The honest "
            "`season_order_week` lives upstream in the P1.3 `feature_pregame_matrix`; the serving "
            "path would have to carry it through, and the alias would have to go."
            if aliases else
            f"`{_SNAPSHOT_PY.name}` derives `{STUDY_WEEK_COL}` honestly (no raw-`week` alias), so "
            "the study's cell is reproducible at score time."),
        "false_pass_note": (
            "⚠️ This leg's FIRST implementation was a substring check (`col in source`) and it "
            "PASSED — satisfied by the alias assignment itself. A name-match cannot distinguish a "
            "column from an alias of the column it forbids; the AST read can. Recorded because the "
            "near-miss is the finding (NF1.7 (a) / INC-38)."),
    }


def run() -> dict[str, Any]:
    legs = [leg_i_expressibility(), leg_ii_quantity(), leg_iii_week_column()]
    ok = all(l["ok"] for l in legs)
    out = {
        "story": _STORY, "checked_at": date.today().isoformat(),
        "parity_holds": ok,
        "recommendation": ("PRE_OPENER_SHIP_PERMITTED (operator approval still required)" if ok
                           else "DEPLOY_HELD"),
        "legs": legs,
        "failing_legs": [l["leg"] for l in legs if not l["ok"]],
        "note": ("§8 of the pre-registration: a pre-opener ship needs BOTH this parity check AND "
                 "explicit operator approval. Any leg failing ⇒ DEPLOY-HELD with the gap named, "
                 "shipping post-opener via the P1.4 serve path. ⛔ This module writes no served "
                 "artifact and changes nothing."),
    }
    _OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(f"=== {_STORY} — parity {'HOLDS' if ok else 'DOES NOT HOLD'} "
          f"⇒ {out['recommendation']} ===")
    for l in legs:
        print(f"\n  [{'✅' if l['ok'] else '❌'}] {l['leg']}")
        print(f"      {l['finding']}")
    print(f"\n  → {_OUT_JSON.relative_to(B._PROJECT_ROOT)}")
    return out


if __name__ == "__main__":
    run()
