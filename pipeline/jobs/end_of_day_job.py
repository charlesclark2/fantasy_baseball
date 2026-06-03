"""End-of-day posterior update job (Epic O.4 / Epic 16.4).

Fan-out: the three sequential-posterior updates run off a single games-check gate.
They write to different tables (player_sequential_posteriors,
team_sequential_posteriors, matchup_cell_sequential_posteriors) with no
inter-dependency, so no fan-in is needed. in_process_executor runs them
sequentially in topological order regardless.
"""

from dagster import in_process_executor, job

from pipeline.ops.end_of_day_ops import (
    check_games_yesterday,
    update_matchup_cell_posteriors_op,
    update_player_posteriors_op,
    update_team_posteriors_op,
)


@job(executor_def=in_process_executor)
def end_of_day_job():
    has_games = check_games_yesterday()
    update_player_posteriors_op(has_games)
    update_team_posteriors_op(has_games)
    update_matchup_cell_posteriors_op(has_games)
