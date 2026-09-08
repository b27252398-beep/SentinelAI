# Architecture Decision Records (ADR)

## ADR 0001: Use of a Modular Monolith over Microservices
**Date**: 2026-09-08
**Status**: Accepted

### Context
SentinelAI involves many distinct domains (auth, telemetry, AI, anomaly detection). There is a temptation to start with microservices to reflect this domain separation.

### Decision
We will build SentinelAI as a modular monolith in Python (FastAPI). 

### Consequences
- **Positive**: Simplifies local development, deployment, and testing during Phase 1. Reduces operational overhead and cross-service communication complexities.
- **Negative**: Requires strict discipline to avoid tight coupling between modules (e.g., `auth` should not directly depend on `anomaly`).
- **Mitigation**: We will enforce strict module boundaries using directory structures and dependency rules.

## ADR 0014: Strict AI Output Categorization
**Date**: 2026-09-08
**Status**: Accepted

### Context
Using LLMs for root-cause analysis can lead to "hallucinations" where the AI presents guesses as facts, which is dangerous for production incident resolution.

### Decision
The AI investigation layer will enforce a strict structured output requirement. All AI responses must separate:
1. **Observed Fact**: Directly measured system evidence.
2. **Inference**: A conclusion derived from evidence.
3. **Recommendation**: A proposed action.

### Consequences
- **Positive**: Increases engineer trust in the platform. Allows safe review of recommendations.
- **Negative**: Increases prompt complexity and requires more sophisticated parsing logic.

## ADR 0012: Anomaly Detection Strategy (Deterministic vs ML)
**Date**: 2026-09-08
**Status**: Accepted

### Context
SentinelAI needs to detect anomalies across varied telemetry inputs. We must decide between adopting complex multivariate machine learning (like Isolation Forests) or deterministic statistical models for the MVP.

### Decision
The MVP will exclusively implement Static Thresholds and Statistical Baselines (Z-Score/Moving Average). Isolation Forests and advanced ML are deferred.

### Consequences
- **Positive**: Eradicates cold-start training delays. Output is 100% mathematically explainable via simple variables (mean, deviation), which cleanly feeds the future AI investigator. Avoids complex MLOps pipelines.
- **Negative**: Less capable of detecting subtle, multi-dimensional correlations (e.g., latency slightly increases *while* CPU slightly decreases).

## ADR 0013: Decoupling Detection via Dedicated Worker Process
**Date**: 2026-09-08
**Status**: Accepted

### Context
Detection algorithms require aggregate queries over time windows. If executed synchronously during `POST /api/v1/telemetry/ingest`, ingestion latency would skyrocket, and database deadlocks could occur. Furthermore, embedding schedulers directly inside FastAPI workers risks duplicate executions when the API is scaled horizontally.

### Decision
Anomaly detection will execute in a dedicated, independent Python worker process deployed alongside the API within the modular monolith topology. Coordination will be managed via Redis distributed locks (e.g., `SET lock:detection:{service_id}:{window_start} NX EX 60`) to enforce mutual exclusion and guarantee at-most-one concurrent execution per window. The architecture mandates strict idempotency; if a lock expires during a worker crash, a subsequent retry will safely update existing anomaly state using PostgreSQL conflict constraints rather than generating duplicates. Heavy queue infrastructure like Kafka or Celery is explicitly rejected.

### Consequences
- **Positive**: Complete isolation of ingestion latency from analytical detection load. Mutual exclusion prevents concurrent collisions. Database idempotency guarantees safe retries without ghost anomalies.
- **Negative**: Introduces a small detection latency (e.g., 1-5 minutes) and requires Redis as an explicit coordination dependency.
