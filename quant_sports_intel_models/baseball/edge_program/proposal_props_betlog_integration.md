# Proposal — Connect the Props (K-projection) surface to the Bet Log

_Draft for the PM Claude session to turn into a scoped story. Not yet in `story_prompts.md`._
_Author context: follows E5.5 (pitcher K-projection transparency surface + daily `/props` page)._

## Why
The `/props` page (and per-pitcher `/props/[id]` detail) now shows the calibrated E5.2 strikeout
projection next to the book's posted line. Users have asked to **log a strikeout prop they're tracking
straight from the Props page into the Bet Log**, instead of re-entering it by hand. This closes the
loop between "here's our projection vs the market" and the user's own bookkeeping.

## 🔒 Non-negotiable framing guardrail (carry over from E5.5)
E5.4 proved the K prop has **no cashable edge** (`best_alpha = 0`). So this integration is a
**bookkeeping convenience**, NOT a bet recommendation:
- The CTA is "Log this prop" / "Track this line" — never "Bet this", "+EV", "value", or any win-rate /
  profitability language. The existing honest-framing guard (`test_k_projection_serving.py`,
  `_BANNED_RE`) should be extended to scan any new bet-log-from-props UI.
- The logged record stores the **user's** line/stake/odds as self-reported bookkeeping. We may store
  our projection alongside for the user's own reference, but must not present it as an edge.
- `automated_bets` stays `false` (US bets are always manual — see the standing rule).

## Scope (proposed)
1. **Frontend — "Log this prop" action** on the `/props/[id]` detail (and optionally each card):
   opens the existing bet-entry form pre-filled with market = pitcher strikeouts, the pitcher, the
   game, and the posted line/book the user is viewing. User edits stake/odds/side and saves.
2. **Bet-log schema** — confirm the bet-log write path supports a player-prop market type
   (pitcher_strikeouts) with: player_id, game_pk, line, side (over/under), odds, book, stake. If the
   current schema is game-market only (h2h/totals), this is the main backend lift — add a prop market
   type to the bet model + settlement.
3. **Settlement** — settle a logged K prop against the pitcher's actual strikeouts
   (`mart_starting_pitcher_game_log.strikeouts`) once the game is final: over/under/push vs the logged
   line. Wire into the existing `settle_user_bets` op (WARN tier).
4. **Optional** — surface "you logged this" state back on the Props surface for that user/date.

## Open questions for the PM
- Does the current Bet Log data model already have a generic market/line/side shape, or is it
  hardcoded to game markets? (Determines whether this is mostly frontend, or a schema + settlement
  story.)
- Should logging be available from the compact card, or only the detail page? (Recommend detail page
  first — less clutter, clearer context.)
- Do we store our projection snapshot with the logged bet for the user's later reference? (Nice-to-have;
  keep it clearly labeled "our projection at log time", not an edge claim.)

## Rough size
- If the bet-log model already supports props: **small** (frontend prefill + a settlement branch).
- If props are a new market type in the bet model: **medium** (schema + settlement + frontend), best
  as its own story with a settlement backfill.

## Touch points (for scoping)
- Frontend: `frontend/app/props/[pitcherId]/page.tsx`, the bet-entry form/component, `frontend/app/bet-log/`.
- Backend: `app/backend/routers/bets.py` (or wherever bet writes live), the bet pydantic model, the
  `settle_user_bets` op.
- Data: `mart_starting_pitcher_game_log.strikeouts` for settlement.
- Guard: extend the honest-framing banned-language scan to the new UI.
