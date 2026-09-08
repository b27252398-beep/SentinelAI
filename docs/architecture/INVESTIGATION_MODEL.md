# Investigation Data Model

The investigation lifecycle tracks how raw telemetry is transformed into actionable intelligence.

## Lifecycle Flow
`Incident → Investigation → Evidence → Hypotheses → Root Cause → Recommendation → Human Decision → Resolution`

## Entity Relationships
1. **Incident**: The highest-level container (e.g., "API Latency Spike in Order Service").
2. **Investigation**: A specific execution of the AI workflow. An incident can have multiple investigations if new data arrives or a user manually re-triggers it. Every investigation explicitly records the `prompt_version` and `model_identifier` used, ensuring AI outputs are auditable and reproducible.
3. **Evidence**: Raw telemetry (logs, metrics, traces) explicitly queried and frozen in time for the investigation. This evidence is promoted and persisted independently from raw telemetry to guarantee that standard telemetry cleanup (e.g., 7-day retention) does not delete critical investigation context. This constitutes **OBSERVED** facts.
4. **Hypothesis**: AI-generated **INFERRED** conclusions attempting to explain the evidence. The system strictly prevents inferences from being conflated with observed facts.
5. **Root Cause**: The hypothesis (or hypotheses) marked by the AI (or explicitly selected by the Engineer) as the primary cause (`is_root_cause = True`).
6. **Recommendation**: Actionable steps attached to a Root Cause.
7. **Human Decision**: Manager approval or rejection of a recommendation.

## State Transitions
- **Investigation Status**: `pending` → `running` → `complete` (or `failed`).
- **Incident Status**: `open` (unassigned) → `investigating` (assigned/active) → `resolved` (mitigated).
