# NF-INJ3b-SHIP — DRAFTED changelog entry (⛔ NOT committed)

Week key **2026-08-24** (a Monday — 2026-08-24 IS Monday, so this opens a NEW week block in `frontend/data/changelog.json`).

⛔ **DRAFTED, NOT COMMITTED — deliberately.** The NF-INJ3c convention: a declaration must not outrun its production. This board is DEPLOY-HELD; nothing has been published. The operator adds this entry as the FINAL step of the publish path, and only on that path. If the flip is held or rolled back, this file is simply deleted and no user-facing claim was ever made.

⚠️ The changelog guard (`betting_ml/tests/test_changelog_guard.py`) fails the build on a non-Monday `week` key or a duplicate Monday, and the render auto-snaps and merges same-week blocks — so if another story has already opened 2026-08-24, MERGE this item into that block's `items` array rather than adding a second block.

```json
{
  "tag": "improved",
  "text": "Players who are on injured reserve or PUP now get a projected-games figure fitted from what players in that situation have actually gone on to play, rather than a fixed cap we chose by hand. The old handling gave every flagged player at a given status the same ceiling; the new one reads how the season is set up for him — whether he ended last season already carrying the same designation, how long it has been since he last played, and how much he played and produced last year — and prices the chance he does not appear at all separately from how much he plays if he does. On this board it moves 22 players, by about two and a half games each. We want to be exact about two things. First, this changes only players carrying a formal IR or PUP designation: suspensions and the non-football-injury list keep the old handling, because there are no players on our board in those situations to have tested it on, and rookies are untouched. Second, a lower games figure does not always move a player's projected points by the same amount — the step that assigns each position's point levels can hand some of it back — so on a few rows you will see the games drop while the points barely move. That is a known gap we have measured and are working on, not something the games figure is hiding. It is not a medical opinion and carries no view on when anyone plays again."
}
```

## Why it is worded this way

- **No win-rate, edge or accuracy claim.** `best_alpha = 0`; the study cleared a calibration and scoring gate, not a betting one, and the copy says what changed rather than that it is better.
- **The boundary is stated, not implied.** SUS/NFI keep the incumbent constants and rookies are untouched — a reader who is looking at a suspended player needs to know this did not reach him.
- **The give-back is disclosed rather than hidden.** Five of the 22 have their games nearly halved with points essentially unchanged; a drafter WILL see that pair and it would be worse to let them discover it than to name it (NF-INJ1 / NF-INJ2b own the fix).
- **No medical framing**, matching every sibling entry in this family.
