# ADR 0009: Telemetry Retention

## Context
Raw telemetry (logs, metrics, traces) grows exponentially. We need a cleanup strategy that prevents the database from overflowing but ensures historical incident investigations remain intact and auditable.

## Decision
1. Raw telemetry will have a default retention period of **7 days**, configurable via environment variables.
2. A background scheduled job will routinely prune raw telemetry older than the retention threshold.
3. Telemetry explicitly queried and used as evidence for an AI investigation will be promoted/copied into the `investigation_evidence` table. This independent persistence ensures raw data cleanup never deletes backing evidence for incidents, hypotheses, or recommendations.

## Alternatives
- Store telemetry forever: Too expensive and impractical for PostgreSQL.
- Soft-delete telemetry: Doesn't solve the storage space issue.
- Delete all telemetry unconditionally: Violates auditability requirements if an old incident's evidence is erased.

## Consequences
- Requires duplicating a small fraction of telemetry into `investigation_evidence`.
- Keeps the raw telemetry tables small and performant.
- Satisfies strict audit and reproducibility requirements.
