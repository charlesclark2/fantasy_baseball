# NF-ROS1 — pre-registration amendment 2 (team resolution, committed BEFORE any scoring)

Amends amendment 1 item 5. The first smoke REFUSED in frame assembly — before any arm, anchor or
residual was computed — because 4.55% of player-weeks (2019–2021) had no schedule team, above the
registered 1% bound. The refusal worked as designed; the cause is two data-shape facts, measured
on the board/schedule/realized TEAM columns only:

* `LAR` on the boards vs `LA` in `schedules` (37 board rows) — the NF-W3 franchise-code class.
  Realized `team` codes all resolved.
* 231 board rows carry NO team (players unsigned when the board was built).

Resolution, fixed here:

1. **One canon on all three sides.** Board `team_id`, realized `team` and schedule
   `home_team`/`away_team` are folded through `quant_sports_intel_models.football.nfl.entity.names.normalize_team`
   (the repo's franchise-level alias map: `LA`/`STL`→`LAR`, `OAK`→`LV`, `SD`→`LAC`, …). Games per
   team per season are franchise-level, so the fold is exact.
2. **Team-less, not-yet-played player-weeks.** When a player has no realized row through week k and
   no board team, his `t` and `G_rem` are the MEDIAN across that season's teams at week k
   (`team_basis = "league_median"`), flagged and counted. He stays in the population: dropping
   unsigned players would remove exactly the rows whose truth is mostly zero, flattering every arm.
   His prior `a0` and `r0` come from the board as for anyone else.
3. The 1% refusal still applies to anything unresolved after 1–2.
