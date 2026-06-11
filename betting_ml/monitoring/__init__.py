"""betting_ml.monitoring — deployed-model health metrics & gates.

Lives inside the installable `betting_ml` package (not loose under scripts/) so it
is importable from the Dagster code location in production, where only packaged
code ships. See model_health_metrics for the honest live-skill evaluate()/gate.
"""
