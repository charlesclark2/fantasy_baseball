import sys
from pathlib import Path

from dagster import AssetExecutionContext, Config, MetadataValue, Output, asset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class OffenseV1TrainConfig(Config):
    promote: bool = True
    optuna_trials: int = 50
    force_winner: str = ""  # "ridge" | "lgbm" | "" (auto)


@asset(
    compute_kind="python",
    group_name="ml_training",
    description="Retrain the offense_v1 sub-model. On-demand only — no schedule.",
)
def offense_v1_model(
    context: AssetExecutionContext,
    config: OffenseV1TrainConfig,
) -> Output[str]:
    from betting_ml.scripts.offense_v1.train_offense_v1 import train

    force_winner = config.force_winner or None
    context.log.info(
        "Starting offense_v1 retrain  promote=%s  optuna_trials=%d  force_winner=%s",
        config.promote,
        config.optuna_trials,
        force_winner,
    )

    mlflow_run_id = train(
        promote=config.promote,
        optuna_trials=config.optuna_trials,
        force_winner=force_winner,
    )

    context.log.info("offense_v1 training complete  mlflow_run_id=%s", mlflow_run_id)
    return Output(
        value=mlflow_run_id,
        metadata={"mlflow_run_id": MetadataValue.text(mlflow_run_id)},
    )


class RunEnvV3TrainConfig(Config):
    promote: bool = True
    force_winner: str = ""   # "ridge" | "xgb" | "" (auto)
    refresh_cache: bool = False


@asset(
    compute_kind="python",
    group_name="ml_training",
    description="Retrain the run_env_v3 sub-model (Ridge vs XGBoost, era features). On-demand only — no schedule.",
)
def run_env_v3_model(
    context: AssetExecutionContext,
    config: RunEnvV3TrainConfig,
) -> Output[str]:
    from betting_ml.scripts.train_run_env_v3 import train

    force_winner = config.force_winner or None
    context.log.info(
        "Starting run_env_v3 retrain  promote=%s  force_winner=%s  refresh_cache=%s",
        config.promote,
        force_winner,
        config.refresh_cache,
    )

    mlflow_run_id = train(
        promote=config.promote,
        force_winner=force_winner,
        refresh_cache=config.refresh_cache,
    )

    context.log.info("run_env_v3 training complete  mlflow_run_id=%s", mlflow_run_id)
    return Output(
        value=mlflow_run_id,
        metadata={"mlflow_run_id": MetadataValue.text(mlflow_run_id)},
    )
