# ADR 0007: Conventional Anomaly Detection + LLM

## Context
LLMs are expensive and slow. Using them to parse gigabytes of raw logs in real-time to find an anomaly is unfeasible.

## Decision
Use deterministic, conventional statistical methods (thresholds, moving averages) for real-time anomaly detection. Only trigger the LLM workflow *after* an incident is created and correlated.

## Alternatives
- LLM for everything: Prohibitively expensive and high latency.
- No LLM: Loses the intelligent RCA capability.

## Consequences
Creates a two-tier system: fast/cheap detection, slow/smart investigation.
