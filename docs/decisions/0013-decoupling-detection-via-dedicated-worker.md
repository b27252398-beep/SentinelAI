# ADR 0013: Decoupling Detection via Dedicated Worker Process

## Context
Detection algorithms require aggregate queries over time windows. If executed synchronously during `POST /api/v1/telemetry/ingest`, ingestion latency would skyrocket, and database deadlocks could occur. Furthermore, embedding schedulers directly inside FastAPI workers risks duplicate executions when the API is scaled horizontally.

## Decision
Anomaly detection will execute in a dedicated, independent Python worker process deployed alongside the API within the modular monolith topology. Coordination will be managed via Redis distributed locks (e.g., `SET lock:detection:{service_id}:{window_start} NX EX 60`) to enforce mutual exclusion and guarantee at-most-one concurrent execution per window. The architecture mandates strict idempotency; if a lock expires during a worker crash, a subsequent retry will safely update existing anomaly state using PostgreSQL conflict constraints rather than generating duplicates. Heavy queue infrastructure like Kafka or Celery is explicitly rejected.

## Consequences
- **Positive**: Complete isolation of ingestion latency from analytical detection load. Mutual exclusion prevents concurrent collisions. Database idempotency guarantees safe retries without ghost anomalies.
- **Negative**: Introduces a small detection latency (e.g., 1-5 minutes) and requires Redis as an explicit coordination dependency.
