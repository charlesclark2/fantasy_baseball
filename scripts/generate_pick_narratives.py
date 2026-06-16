"""generate_pick_narratives.py
Generates natural-language narratives for today's picks using Snowflake Cortex COMPLETE.
Run AFTER predict_today.py completes (same Dagster job, next op).

Generates ONCE per (game_pk, game_date, prediction_type) — cached in pick_narrative column.
Skips rows that already have a narrative, so safe to re-run.

Cost-conscious: uses mistral-7b (cheapest Cortex model); ~15–30 games/day = negligible spend.

Usage:
    uv run python scripts/generate_pick_narratives.py
    uv run python scripts/generate_pick_narratives.py --date 2026-06-16
    uv run python scripts/generate_pick_narratives.py --date 2026-06-16 --schema dev

BEFORE MERGING: test with dev schema first:
    uv run python scripts/generate_pick_narratives.py --date 2026-06-16 --schema dev
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from datetime import date as _date
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def _load_private_key() -> bytes:
    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        with open(pk_path, "rb") as fh:
            pem_bytes = fh.read()
    else:
        key_val = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
        if not key_val:
            raise RuntimeError("Neither SNOWFLAKE_PRIVATE_KEY_PATH nor SNOWFLAKE_PRIVATE_KEY is set")
        if not key_val.startswith("-----"):
            key_val = base64.b64decode(key_val).decode("utf-8")
        pem_bytes = key_val.encode("utf-8")
    p_key = serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _connect_snowflake() -> snowflake.connector.SnowflakeConnection:
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database="baseball_data",
        private_key=_load_private_key(),
    )
    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role
    return snowflake.connector.connect(**kwargs)

_SYSTEM_PROMPT = """\
You write sharp, analytical explanations of why a baseball model landed on a prediction.

Rules:
- Lead with the SINGLE most influential factor. Name what it is and why it tips the scale for this matchup.
- Ground the narrative in the win probability and/or projected total — use these EXACT numbers.
- If a strong counter-signal exists, acknowledge the tension briefly.
- Be specific to this game and these teams. Never write something that could apply to any game.
- Do NOT open with "The model", "The model is", or "The model analyzes". Vary your construction.
- Do NOT use the words: guaranteed, win rate, profit, edge, sure bet, prediction, algorithm.
- Write for a sports-savvy reader, not a data scientist. Explain what wOBA/xwOBA means in parentheses if you use it.

YOUR RESPONSE MUST:
- Be at least 3 complete sentences.
- Include the win probability as a percentage (e.g., "63% win probability") OR the projected total runs (e.g., "6.9 projected runs").
- Reference at least one specific numeric value from the driver data (run contribution, probability, etc.).
- Name both teams explicitly — not just "the home team" or "the model's pick."
- NEVER collapse to a single sentence summary. NEVER omit numbers.
"""

_STRENGTH_LABEL = [
    (0.75, "dominant signal"),
    (0.40, "strong factor"),
    (0.20, "supporting factor"),
    (0.00, "minor factor"),
]

_NO_PICK_NARRATIVE = (
    "The model does not have a conviction pick for this game. Make picks at your own discretion."
)


def _strength(rel: float) -> str:
    for threshold, label in _STRENGTH_LABEL:
        if rel >= threshold:
            return label
    return "minor factor"


def _resolve_label(label: str, home: str, away: str) -> str:
    """Replace generic 'Home'/'Away' prefixes with actual team names so the LLM
    can reason about which team each driver favors without guessing."""
    label = label.replace("Home bullpen", f"{home} bullpen")
    label = label.replace("Away bullpen", f"{away} bullpen")
    label = label.replace("Home starter", f"{home} starter")
    label = label.replace("Away starter", f"{away} starter")
    label = label.replace("Home pit ", f"{home} pitching ")
    label = label.replace("Away pit ", f"{away} pitching ")
    label = label.replace("Home lineup", f"{home} lineup")
    label = label.replace("Away lineup", f"{away} lineup")
    label = label.replace("Home team", f"{home} team")
    label = label.replace("Away team", f"{away} team")
    # Lowercase "home"/"away" variants
    label = label.replace("home bullpen", f"{home} bullpen")
    label = label.replace("away bullpen", f"{away} bullpen")
    label = label.replace("home starter", f"{home} starter")
    label = label.replace("away starter", f"{away} starter")
    return label


def _format_drivers_structured(
    drivers: list[dict],
    units: str = "relative",
    home: str = "Home",
    away: str = "Away",
) -> str:
    """Format drivers with relative magnitude labels and clear direction language.

    units="runs"    → show actual run contribution so the LLM can reference magnitudes
    units="relative" → show only relative strength (h2h log-odds are not intuitive)
    """
    if not drivers:
        return "  (none)"
    sorted_d = sorted(drivers, key=lambda d: abs(d.get("contribution", 0)), reverse=True)
    max_abs = max(abs(d.get("contribution", 0)) for d in sorted_d) or 1.0
    lines = []
    for d in sorted_d[:6]:
        abs_c = abs(d.get("contribution", 0))
        rel = abs_c / max_abs
        direction = d.get("direction", "increases")
        raw_label = d.get("label", d.get("feature", ""))
        label = _resolve_label(raw_label, home, away)
        family = d.get("family", "")
        toward = d.get("toward", "prediction")

        # Make direction unambiguous — LLM saw "pushes toward" even for decreases
        if direction == "increases":
            arrow = "↑ raises"
        else:
            arrow = "↓ lowers"

        # For totals, show actual run magnitude — 1.8 runs is meaningful context
        mag_str = ""
        if units == "runs":
            mag_str = f" ({d.get('contribution', 0):+.2f} runs)"

        lines.append(
            f"  [{_strength(rel)}] {label} ({family}){mag_str} → {arrow} {toward}"
        )
    return "\n".join(lines)


_H2H_RULE_DESCRIPTIONS = {
    "direction_flip": (
        "CONTRARIAN — the model favors a DIFFERENT team than the market. "
        "The model is explicitly betting against the market's consensus pick."
    ),
    "magnitude": (
        "CONFIRMATION — model and market agree on the favored team, but the model assigns "
        "meaningfully higher win probability than market implied odds suggest."
    ),
}


def _layer4_section(row: dict, home: str, away: str, favored: str | None) -> str:
    """Build a plain-English description of what Layer 4 triggered."""
    lines = []

    h2h_decision = (row.get("LAYER4_H2H_DECISION") or "").lower().strip()
    h2h_rule = (row.get("LAYER4_H2H_RULE") or "").lower().strip()
    tot_decision = (row.get("LAYER4_TOTALS_DECISION") or "").lower().strip()

    if h2h_decision and h2h_decision != "abstain":
        side = home if h2h_decision == "home" else away
        rule_desc = _H2H_RULE_DESCRIPTIONS.get(h2h_rule, f"rule: {h2h_rule}")
        lines.append(f"  H2H bet signal: {side} to win. {rule_desc}")

    if tot_decision and tot_decision != "abstain":
        direction = "OVER" if tot_decision == "over" else "UNDER"
        lines.append(
            f"  Totals bet signal: {direction}. "
            f"The model projects the combined run total {'above' if tot_decision == 'over' else 'below'} the book line."
        )

    if not lines:
        return ""

    return "\nBet conviction signals (what the model's gate flagged for this game):\n" + "\n".join(lines)


def _build_prompt(row: dict, expl: dict) -> str | None:
    """Build the Cortex prompt for one game row."""
    import math

    home = row.get("HOME_TEAM") or "Home"
    away = row.get("AWAY_TEAM") or "Away"
    targets = expl.get("targets", {})

    hw = targets.get("home_win", {})
    tot = targets.get("total_runs", {})

    hw_drivers = hw.get("drivers", [])
    tot_drivers = tot.get("drivers", [])

    if not hw_drivers and not tot_drivers:
        return None

    hw_pred = hw.get("prediction")
    tot_pred = tot.get("prediction")

    hw_prob_str = ""
    favored = None
    if hw_pred is not None:
        try:
            hw_prob = 1.0 / (1.0 + math.exp(-float(hw_pred)))
            favored = home if hw_prob >= 0.5 else away
            underdog = away if favored == home else home
            hw_prob_str = (
                f"Win probability: {favored} {hw_prob * 100:.0f}% / {underdog} {(1 - hw_prob) * 100:.0f}%."
            )
        except Exception:
            hw_prob_str = ""

    tot_str = ""
    if tot_pred is not None:
        tot_str = f"Projected total runs: {float(tot_pred):.1f}."

    context_parts = [f"Game: {away} @ {home} (home: {home})."]
    if hw_prob_str:
        context_parts.append(hw_prob_str)
    if tot_str:
        context_parts.append(tot_str)
    context = " ".join(context_parts)

    layer4_section = _layer4_section(row, home, away, favored)

    hw_section = ""
    if hw_drivers:
        hw_section = (
            f"\nFactors shaping the win-probability — ranked by influence (dominant → minor):\n"
            f"(↑ raises = pushes model toward {home} winning; ↓ lowers = pushes model toward {away} winning)\n"
            + _format_drivers_structured(hw_drivers, units="relative", home=home, away=away)
        )

    tot_section = ""
    if tot_drivers:
        tot_pred_val = tot.get("prediction")
        base_val = tot.get("base_value")
        total_shift = ""
        if tot_pred_val is not None and base_val is not None:
            try:
                shift = float(tot_pred_val) - float(base_val)
                total_shift = f" (league baseline {float(base_val):.1f} runs; model projects {float(tot_pred_val):.1f} runs, a {shift:+.1f} run shift)"
            except Exception:
                pass
        tot_section = (
            f"\nFactors shaping the run-total projection{total_shift} — ranked by influence:\n"
            "(Contributions are in runs — e.g. −1.8 means that factor alone pulls the total down by 1.8 runs)\n"
            + _format_drivers_structured(tot_drivers, units="runs", home=home, away=away)
        )

    # Tailor the closing instruction to what the model actually flagged
    h2h_decision = (row.get("LAYER4_H2H_DECISION") or "").lower().strip()
    h2h_rule = (row.get("LAYER4_H2H_RULE") or "").lower().strip()
    tot_decision = (row.get("LAYER4_TOTALS_DECISION") or "").lower().strip()

    instruction_parts = [
        "Write 2–3 sentences explaining what's driving this prediction. "
        "Lead with the dominant signal and name the teams."
    ]
    if h2h_rule == "direction_flip":
        instruction_parts.append(
            "Prominently explain that the model is taking a contrarian position — "
            "it disagrees with the market on which team is favored, and why the underlying factors justify that."
        )
    elif h2h_rule == "magnitude":
        instruction_parts.append(
            "Note that the model agrees with the market's pick but sees the edge team more clearly — "
            "explain what's giving the model extra conviction."
        )
    if tot_decision and tot_decision != "abstain":
        direction = "over" if tot_decision == "over" else "under"
        instruction_parts.append(
            f"Explain why the model is projecting a {direction} — which factors are pushing the total in that direction."
        )

    prompt = (
        f"{_SYSTEM_PROMPT}\n"
        f"---\n"
        f"{context}"
        f"{layer4_section}"
        f"{hw_section}"
        f"{tot_section}\n"
        f"---\n"
        + " ".join(instruction_parts)
    )
    return prompt


# ---------------------------------------------------------------------------
# Quality gate — minimum bar for a Cortex response before writing to DB
# ---------------------------------------------------------------------------

_MIN_CHARS = 240
_MIN_SENTENCES = 3

_RETRY_PREFIX = (
    "Your previous response was too brief or lacked specific numbers. "
    "You MUST write at least 3 complete sentences. "
    "You MUST include the win probability as a percentage and/or the projected run total. "
    "Reference specific numeric values — do not write vague statements without numbers.\n\n"
)


def _quality_check(text: str) -> bool:
    """Return True if the narrative meets minimum quality bars."""
    text = text.strip()
    if len(text) < _MIN_CHARS:
        return False
    sentence_endings = text.count(".") + text.count("!") + text.count("?")
    if sentence_endings < _MIN_SENTENCES:
        return False
    if not any(c.isdigit() for c in text):
        return False
    return True


def _template_narrative(row: dict, expl: dict) -> str:
    """Deterministic fallback when both Cortex attempts fail quality checks.
    Always informative — references actual probabilities, run totals, and top driver."""
    import math

    home = row.get("HOME_TEAM") or "Home"
    away = row.get("AWAY_TEAM") or "Away"
    targets = expl.get("targets", {})
    hw = targets.get("home_win", {})
    tot = targets.get("total_runs", {})

    h2h_dec = (row.get("LAYER4_H2H_DECISION") or "").lower().strip()
    h2h_rule = (row.get("LAYER4_H2H_RULE") or "").lower().strip()
    tot_dec = (row.get("LAYER4_TOTALS_DECISION") or "").lower().strip()

    parts = []

    # H2H block
    hw_pred = hw.get("prediction")
    if hw_pred is not None and h2h_dec and h2h_dec != "abstain":
        try:
            hw_prob = 1.0 / (1.0 + math.exp(-float(hw_pred)))
            favored = home if h2h_dec == "home" else away
            underdog = away if favored == home else home
            fav_prob = hw_prob if h2h_dec == "home" else 1.0 - hw_prob

            hw_drivers = hw.get("drivers", [])
            top = max(hw_drivers, key=lambda d: abs(d.get("contribution", 0)), default=None)
            top_label = _resolve_label(top["label"], home, away) if top else None

            if h2h_rule == "direction_flip":
                opener = (
                    f"Against the market consensus, the model favors {favored} "
                    f"({fav_prob * 100:.0f}% win probability) over {underdog}."
                )
            else:
                opener = (
                    f"The model favors {favored} ({fav_prob * 100:.0f}% win probability) "
                    f"over {underdog}, with stronger conviction than the market implies."
                )

            if top_label:
                direction_verb = "anchoring" if top.get("direction") == "increases" and h2h_dec == "home" else "driving"
                parts.append(
                    f"{opener} The dominant signal {direction_verb} this lean is "
                    f"{top_label} ({top.get('family', '')}), the model's largest single influence on the outcome."
                )
            else:
                parts.append(opener)
        except Exception:
            pass

    # Totals block
    tot_pred = tot.get("prediction")
    tot_base = tot.get("base_value")
    if tot_pred is not None and tot_dec and tot_dec != "abstain":
        try:
            direction = "over" if tot_dec == "over" else "under"
            shift = float(tot_pred) - float(tot_base) if tot_base is not None else None
            shift_str = (
                f" ({shift:+.1f} runs from the {float(tot_base):.1f}-run league baseline)"
                if shift is not None else ""
            )

            tot_drivers = tot.get("drivers", [])
            top_t = max(tot_drivers, key=lambda d: abs(d.get("contribution", 0)), default=None)

            tot_str = (
                f"On the total, the model projects {float(tot_pred):.1f} runs{shift_str}, "
                f"flagging the {direction}."
            )
            if top_t:
                contrib = top_t.get("contribution", 0)
                top_t_label = _resolve_label(top_t["label"], home, away)
                tot_str += (
                    f" The primary driver is {top_t_label} "
                    f"({contrib:+.2f} runs), the largest single pull on the projection."
                )
            parts.append(tot_str)
        except Exception:
            pass

    return " ".join(parts) if parts else _NO_PICK_NARRATIVE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=_date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--schema", choices=["dev", "prod"], default="dev")
    args = parser.parse_args()

    ml_schema = (
        "baseball_data.betting_ml"
        if args.schema == "prod"
        else "baseball_data.betting_ml_dev"
    )

    log.info("Generating pick narratives for %s (schema=%s)", args.date, args.schema)

    try:
        conn = _connect_snowflake()
    except Exception:
        log.exception("Snowflake connection failed")
        return 1

    cur = conn.cursor()

    # 1. Fetch rows needing narratives
    cur.execute(
        f"""
        SELECT game_pk, home_team, away_team, prediction_type, pick_explanation,
               layer4_h2h_decision, layer4_h2h_rule, layer4_totals_decision
        FROM {ml_schema}.daily_model_predictions
        WHERE game_date = %(date)s
          AND pick_explanation IS NOT NULL
          AND pick_narrative IS NULL
        ORDER BY game_pk, prediction_type
        """,
        {"date": args.date},
    )
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in rows]

    if not rows:
        log.info("No rows needing narratives — nothing to do")
        return 0

    log.info("Generating narratives for %d rows", len(rows))
    success = 0
    skipped = 0
    errors = 0

    for row in rows:
        game_pk = row["GAME_PK"]
        prediction_type = row["PREDICTION_TYPE"]

        raw_expl = row.get("PICK_EXPLANATION")
        if not raw_expl:
            skipped += 1
            continue

        try:
            expl = json.loads(raw_expl) if isinstance(raw_expl, str) else raw_expl
        except (json.JSONDecodeError, TypeError):
            log.warning("Could not parse pick_explanation for game_pk=%s", game_pk)
            skipped += 1
            continue

        # Short-circuit: no Layer 4 signal → static message, no Cortex call
        h2h_dec = (row.get("LAYER4_H2H_DECISION") or "").lower().strip()
        tot_dec = (row.get("LAYER4_TOTALS_DECISION") or "").lower().strip()
        has_signal = (h2h_dec and h2h_dec != "abstain") or (tot_dec and tot_dec != "abstain")

        if not has_signal:
            cur.execute(
                f"""
                UPDATE {ml_schema}.daily_model_predictions
                SET pick_narrative = %(narrative)s
                WHERE game_pk = %(game_pk)s
                  AND game_date = %(date)s
                  AND prediction_type = %(prediction_type)s
                """,
                {
                    "narrative": _NO_PICK_NARRATIVE,
                    "game_pk": game_pk,
                    "date": args.date,
                    "prediction_type": prediction_type,
                },
            )
            conn.commit()
            log.info("No signal for game_pk=%s — wrote static message", game_pk)
            success += 1
            continue

        prompt = _build_prompt(row, expl)
        if not prompt:
            log.info("Skipping game_pk=%s — no drivers", game_pk)
            skipped += 1
            continue

        try:
            # Try Cortex up to 2 times; fall back to deterministic template if both fail
            narrative = None
            for attempt in range(2):
                cortex_prompt = (_RETRY_PREFIX + prompt) if attempt == 1 else prompt
                cur.execute(
                    "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', %s)",
                    [cortex_prompt],
                )
                result = cur.fetchone()
                if not result or not result[0]:
                    log.warning("Empty Cortex response for game_pk=%s attempt=%d", game_pk, attempt + 1)
                    continue

                candidate = str(result[0]).strip()
                if _quality_check(candidate):
                    narrative = candidate
                    log.info("Quality check passed for game_pk=%s attempt=%d", game_pk, attempt + 1)
                    break
                log.info(
                    "Quality check failed for game_pk=%s attempt=%d (len=%d, sentences=%d)",
                    game_pk, attempt + 1, len(candidate),
                    candidate.count(".") + candidate.count("!") + candidate.count("?"),
                )

            if narrative is None:
                log.info("Falling back to template for game_pk=%s", game_pk)
                narrative = _template_narrative(row, expl)

            # Honesty guard: warn if gambling-specific claims slipped through the system prompt.
            # "edge" is intentionally excluded — it appears legitimately in baseball analysis
            # ("pitching edge", "competitive edge") and trimming on it destroys valid narratives.
            for banned in ("guaranteed", "win rate", "sure bet"):
                if banned.lower() in narrative.lower():
                    log.warning("Banned phrase '%s' in narrative for game_pk=%s — keeping narrative, review manually", banned, game_pk)

            cur.execute(
                f"""
                UPDATE {ml_schema}.daily_model_predictions
                SET pick_narrative = %(narrative)s
                WHERE game_pk = %(game_pk)s
                  AND game_date = %(date)s
                  AND prediction_type = %(prediction_type)s
                """,
                {
                    "narrative": narrative,
                    "game_pk": game_pk,
                    "date": args.date,
                    "prediction_type": prediction_type,
                },
            )
            conn.commit()
            log.info("Wrote narrative for game_pk=%s prediction_type=%s", game_pk, prediction_type)
            success += 1

        except Exception:
            log.exception("Cortex call failed for game_pk=%s", game_pk)
            errors += 1

    cur.close()
    conn.close()

    log.info("Done: %d written, %d skipped, %d errors", success, skipped, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
