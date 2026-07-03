from pipeline.assets.dbt_assets import baseball_dbt_assets
# E11.1-W11-E: parlay_historical_matches_catchup DECOMMISSIONED (Parlay platform retired) — asset removed.
from pipeline.assets.training_assets import offense_v1_model, run_env_v3_model
from pipeline.assets.clv_monitoring_asset import clv_monitoring

all_assets = [baseball_dbt_assets, offense_v1_model, run_env_v3_model, clv_monitoring]
