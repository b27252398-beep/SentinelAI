# Telemetry Architecture

The platform relies on structured observability data following the **OpenTelemetry (OTel)** paradigm.

## Data Types
1. **Logs**: Timestamped text records with severity levels and metadata.
2. **Metrics**: Numerical time-series data (e.g., CPU %, Request Latency).
3. **Traces**: Distributed request flows showing span durations across services.

## Ingestion & Normalization
- Telemetry is ingested via a REST API endpoint (`/api/v1/telemetry/ingest`).
- In Phase 1, data is directly persisted to PostgreSQL (using Partitioned tables or JSONB columns) rather than deploying a heavy time-series DB like Prometheus or Elasticsearch. This maintains the MVP monolithic scope while being sufficient for a simulated environment.
- **Correlation Identifiers**: Every log, metric, or trace must include a `service_id` and a `timestamp`. To strictly align with OpenTelemetry standards, tracing identifiers must be preserved as their native OTel formats in the database (e.g., standard Hex Strings):
  - `trace_id`: OTel 128-bit TraceId
  - `span_id`: OTel 64-bit SpanId
  - `parent_span_id`: OTel 64-bit SpanId
- **Idempotency Strategy**: To handle duplicate ingestion safely across logs, metrics, and traces, a deterministic event fingerprint/hash (e.g., SHA-256 of `service_id` + `timestamp` + `payload` + OTel identifiers if present) will be computed and enforced via a unique constraint in the database.

## Telemetry Data Model
The internal conceptual schema distinguishes normalized, easily queryable metadata from the original raw telemetry payload:
- **Normalized / Queryable Metadata**:
  - `id`: SentinelAI telemetry ID (UUID, Primary Key)
  - `service_id`: UUID (Foreign Key to Services)
  - `timestamp`: UTC Timestamp (Event occurrence)
  - `ingestion_timestamp`: UTC Timestamp (Time received by SentinelAI)
  - `telemetry_type`: Enum (log, metric, trace)
  - `trace_id`: 128-bit String (Optional)
  - `span_id`: 64-bit String (Optional)
  - `parent_span_id`: 64-bit String (Optional)
  - `severity`: String or Integer (Optional)
- **Raw / Original Payload**:
  - `resource_attributes`: JSONB (Attributes describing the source, e.g., host/container)
  - `event_attributes`: JSONB (Semantic attributes of the specific event)
  - `raw_payload`: JSONB (The complete unadulterated original payload)

## Making Telemetry Usable
- **Anomaly Detection**: Background workers periodically query metric averages over rolling windows (e.g., 5-minute buckets) and compare against historical baselines.
- **Investigation Retrieval**: When an incident occurs at time $T$, the AI Investigation module queries telemetry for the affected `service_id` within the window $[T-15m, T+5m]$ to extract **Observed Facts**.

## Data Retention & Cleanup
- **Retention Policy**: Raw telemetry (logs, metrics, traces) stored in PostgreSQL has a default retention period of **7 days**.
- **Configurability**: The retention period is configurable via application environment variables (e.g., `TELEMETRY_RETENTION_DAYS=7`).
- **Physical Design (Time Partitioning)**: The telemetry tables will rely on PostgreSQL time-based partitioning. Retention cleanup will occur optimally by dropping old table partitions (e.g., daily partitions). For small MVP setups where partitioning is overkill, a fallback background job (e.g., Celery) using a bulk `DELETE` query will execute the cleanup.
- **Evidence Persistence**: Investigation evidence is promoted and persisted independently from raw telemetry. When an investigation references a telemetry record, a copy of that record is stored in `investigation_evidence`. Therefore, raw telemetry cleanup will never delete the evidence backing an incident investigation, nor will it delete incident records, hypotheses, root causes, recommendations, or audit logs.

## Simulated Environment Strategy
We will build a simple script to generate mock telemetry for services like `api-gateway` and `user-service`. The script will simulate steady-state metrics and subsequently inject anomalies (e.g., spiking error rates, database exhaustion) to accurately test the detection and AI pipelines.
