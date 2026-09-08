# ADR 0012: Anomaly Detection Strategy (Deterministic vs ML)

## Context
SentinelAI needs to detect anomalies across varied telemetry inputs. We must decide between adopting complex multivariate machine learning (like Isolation Forests) or deterministic statistical models for the MVP.

## Decision
The MVP will exclusively implement Static Thresholds and Statistical Baselines (Z-Score/Moving Average). Isolation Forests and advanced ML are deferred.

## Consequences
- **Positive**: Eradicates cold-start training delays. Output is 100% mathematically explainable via simple variables (mean, deviation), which cleanly feeds the future AI investigator. Avoids complex MLOps pipelines.
- **Negative**: Less capable of detecting subtle, multi-dimensional correlations (e.g., latency slightly increases *while* CPU slightly decreases).
