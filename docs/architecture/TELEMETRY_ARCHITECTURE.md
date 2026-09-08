# Telemetry Architecture

The platform relies on structured observability data following the **OpenTelemetry (OTel)** paradigm.

## Data Types
1. **Logs**: Timestamped text records with severity levels and metadata.
2. **Metrics**: Numerical time-series data (e.g., CPU %, Request Latency).
3. **Traces**: Distributed request flows showing span durations across services.

## Ingestion & Normalization
- Telemetry is ingested via a REST API endpoint (`/api/v1/telemetry/ingest`).
- In Phase 1, data is directly persisted to PostgreSQL (using Partitioned tables or JSONB columns) rather than deploying a heavy time-series DB like Prometheus or Elasticsearch. This maintains the MVP monolithic scope while being sufficient for a simulated environment.
- **Correlation Identifiers**: Every log, metric, or trace must include a `service_id` and a `timestamp`. Traces include a `trace_id`.

## Making Telemetry Usable
- **Anomaly Detection**: Background workers periodically query metric averages over rolling windows (e.g., 5-minute buckets) and compare against historical baselines.
- **Investigation Retrieval**: When an incident occurs at time $T$, the AI Investigation module queries telemetry for the affected `service_id` within the window $[T-15m, T+5m]$ to extract **Observed Facts**.

## Data Retention & Cleanup
- **Retention Policy**: Raw telemetry (logs, metrics, traces) stored in PostgreSQL has a default retention period of **7 days**.
- **Configurability**: The retention period is configurable via application environment variables (e.g., `TELEMETRY_RETENTION_DAYS=7`).
- **Cleanup Process**: A background scheduled task (e.g., Celery Beat) periodically deletes raw telemetry older than the retention threshold.
- **Evidence Persistence**: Investigation evidence is promoted and persisted independently from raw telemetry. When an investigation references a telemetry record, a copy of that record is stored in `investigation_evidence`. Therefore, raw telemetry cleanup will never delete the evidence backing an incident investigation, nor will it delete incident records, hypotheses, root causes, recommendations, or audit logs.

## Simulated Environment Strategy
We will build a simple script to generate mock telemetry for services like `api-gateway` and `user-service`. The script will simulate steady-state metrics and subsequently inject anomalies (e.g., spiking error rates, database exhaustion) to accurately test the detection and AI pipelines.
