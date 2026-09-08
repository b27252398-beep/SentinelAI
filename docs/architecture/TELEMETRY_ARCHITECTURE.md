# Telemetry Architecture

The platform relies on structured observability data following the **OpenTelemetry (OTel)** paradigm.

## Data Types
1. **Logs**: Timestamped text records with severity levels and metadata.
2. **Metrics**: Numerical time-series data (e.g., CPU %, Request Latency).
3. **Traces**: Distributed request flows showing span durations across services.

## Ingestion & Normalization
- Telemetry is ingested via a single REST API endpoint (`POST /api/v1/telemetry/ingest`). A single endpoint accepting a `telemetry_type` envelope simplifies the collector pipeline and routing.
- In Phase 1, data is persisted to a unified `telemetry` PostgreSQL table utilizing time-based declarative partitioning. A single table with JSONB payloads minimizes schema migrations when OTel specifications evolve while still allowing index-driven querying on core normalized metadata.

## OpenTelemetry Compatibility
- **Correlation Identifiers**: Every event must include a `service_id` and a `timestamp`. Tracing identifiers must be preserved strictly in their native OTel formats (Hex strings):
  - `trace_id`: 128-bit String (NOT a UUID)
  - `span_id`: 64-bit String (NOT a UUID)
  - `parent_span_id`: 64-bit String (NOT a UUID)
- SentinelAI's internal identifier remains a strictly generated `id` (UUID), but it acts as part of a composite primary key alongside `timestamp` due to PostgreSQL partitioning requirements.

## Telemetry Data Model
The conceptual schema distinguishes normalized, easily queryable relational columns from the raw payload:

### Relational / Queryable Metadata
- `id`: UUID (Part of Composite PK)
- `timestamp`: TIMESTAMPTZ (Event occurrence - Partition Key & Part of Composite PK)
- `service_id`: UUID (Logical Reference to Services)
- `ingestion_timestamp`: TIMESTAMPTZ (Time received by SentinelAI)
- `telemetry_type`: VARCHAR(20) (log, metric, trace)
- `trace_id`: VARCHAR(32) (Optional 128-bit Hex)
- `span_id`: VARCHAR(16) (Optional 64-bit Hex)
- `parent_span_id`: VARCHAR(16) (Optional 64-bit Hex)
- `severity_number`: INTEGER (Optional for Logs)
- `metric_name`: VARCHAR(255) (Optional for Metrics)
- `metric_value`: DOUBLE PRECISION (Optional for Metrics)
- `unit`: VARCHAR(50) (Optional for Metrics)
- `http_status_code`: INTEGER (Optional for web spans). Extracted canonically from `event_attributes.http.response.status_code`, `event_attributes.http.status_code`, or identical fields within `raw_payload.attributes`. Invalid extractions yield NULL.
- `span_kind`: VARCHAR(20) (Optional for traces). **Derived canonical semantic field.** It is not independently client-authoritative. Extracted exclusively from `raw_payload.kind` or `raw_payload.spanKind`. Converts standard integers (1-5) and specific strings (CLIENT, SERVER, PRODUCER, CONSUMER, INTERNAL). Invalid/absent extractions yield NULL.
- `fingerprint`: VARCHAR(64) (Idempotency Hash)

### JSONB / Raw Storage
- `resource_attributes`: JSONB (Attributes describing the source, e.g., host/container)
- `event_attributes`: JSONB (Semantic attributes of the specific event)
- `raw_payload`: JSONB (The complete unadulterated original payload)

## Database Partitioning & Primary Keys
- **Partition Strategy**: Declarative `RANGE` partitioning keyed on the `timestamp` column. The interval is **Daily** (e.g., `telemetry_p2026_09_08`).
- **Primary Key**: PostgreSQL partitioned tables require the partition key to be part of the Primary Key. Therefore, the physical PK is **`PRIMARY KEY(id, timestamp)`**. Do not attempt a parent-level `UNIQUE(id)` constraint, as it conflicts with PostgreSQL partitioning.
- **Global Uniqueness**: The `id` (UUIDv4) is statistically globally unique on its own and serves as the canonical SentinelAI telemetry UUID. The API `GET /api/v1/telemetry/{id}` lookup is supported via an explicit index on `id`.
- **Future References**: Because partitions are aggressively dropped after 7 days, long-lived tables (like `incidents` or `investigation_evidence`) **MUST NOT** use strict database Foreign Keys pointing to `telemetry`. Instead, they will store logical references (the telemetry UUID/timestamp) and perform deep copies of the raw payload into an `evidence` table. 

## Partition Management & Ingestion Window
- **Ingestion Policy Window**: The supported ingestion window is an explicit application policy. For the MVP, this window is approximately **T-7 days through T+2 days**.
- **Boundary Rejections**: Telemetry with timestamps older than T-7 or exceedingly far into the future (> T+2) is explicitly rejected by the application validation layer.
- **Maintenance**: A background cron worker manages partitions, guaranteeing daily partitions are pre-created solely for this supported window. The system explicitly blocks arbitrary partition creation based on attacker-controlled timestamps.

## Idempotency Strategy
To handle duplicate submissions gracefully during batch processing:
- **Composition**: `SHA256(service_id + timestamp.isoformat() + telemetry_type + (trace_id|span_id if present) + SHA256(canonical JSON payload))`
- **Enforcement**: A `UNIQUE(fingerprint, timestamp)` constraint is placed on the partitioned table.
- **Batch Semantics**: Ingestion uses standard `INSERT ... ON CONFLICT (fingerprint, timestamp) DO NOTHING`. This deterministic batch semantic means new events are appended, exact duplicates are silently ignored, and the API safely returns `200 OK` (e.g. `{"accepted": N, "duplicates": M}`) for the batch without crashing or demanding complex client retries.

## Service Lifecycle Compatibility
- **Active Check**: Live telemetry ingestion strictly requires `services.is_active = True`. Payloads referencing archived services are rejected.

## Machine Authentication Design
Machine ingestion strictly utilizes least-privilege service-scoped credentials (`machine_credentials` table):
- `id`: UUID (PK)
- `service_id`: UUID (Nullable). **Service-scoped credentials are the DEFAULT MVP mechanism.** A credential maps to exactly one service and grants `telemetry:ingest`. A global credential (`service_id=NULL`) may exist *only* as an explicitly privileged administrative capability for centralized OpenTelemetry Collector deployments, but it must NEVER be presented as the default.
- `key_prefix`: VARCHAR(16) (Public identifier for ultra-fast lookup).
- `api_key_hash`: VARCHAR(64) (Stores `SHA-256` of the secret).
- `name`: VARCHAR(100)
- `is_active`: BOOLEAN
- `created_at`: TIMESTAMPTZ
- `revoked_at`: TIMESTAMPTZ (Nullable)

**Credential Authentication Flow**:
1. Incoming API token arrives formatted as `prefix.secret`.
2. Application queries DB using the indexed `key_prefix` to efficiently identify the credential record.
3. Application hashes the provided secret via `SHA-256` and compares against `api_key_hash`.
4. Validates `is_active = True`.
5. Validates ingestion scope and bounds against the targeted `service_id`.

## Data Retention & Investigation Evidence
- **Raw Telemetry**: Highly ephemeral. Default retention is **7 days**. Old partitions are dropped physically (`DROP TABLE telemetry_pYYYY_MM_DD`).
- **Investigation Evidence**: Highly durable. Promoted evidence is persisted completely independently. When an anomaly is investigated, crucial telemetry is deep-copied into the `investigation_evidence` schema.
- **Provenance**: `investigation_evidence` stores the raw telemetry UUID as logical provenance metadata only. It survives completely intact when the originating raw telemetry partitions expire and are purged.

## Query API & RBAC
- **`POST /api/v1/telemetry/ingest`**: [Machine Credential Only]. Accepts batches (Max size: 5MB). Yields synchronous `200 OK` (reporting duplicates vs accepted counts).
- **`GET /api/v1/telemetry`**: [All 4 Human Roles]. Supports query parameters (`service_id`, `time_range`, `telemetry_type`, `trace_id`).
- **`GET /api/v1/telemetry/{id}`**: [All 4 Human Roles]. Uses `ix_telemetry_id` to quickly locate the specific row.

## Indexes (MVP Critical)
- `(timestamp)`: Implicitly optimized by partitioning, but local index helps time-range queries.
- `(service_id, timestamp)`: Essential for service-centric time range queries (Anomaly detection).
- `(trace_id)`: Essential for distributed trace correlation.
- `(id)`: Essential for `GET /telemetry/{id}` canonical lookups across partitions.
- `(fingerprint, timestamp)`: Required for the UNIQUE constraint supporting idempotency.
- `(key_prefix)`: Crucial for blazing-fast Machine Credential lookups.

## Ingestion Validation & Error Model
- **200 OK**: Batch successfully processed synchronously. Response denotes `accepted` and `duplicates`.
- **401 Unauthorized**: Invalid or missing Machine API Key.
- **403 Forbidden**: Target service is archived, API Key is revoked, or a service-scoped key attempts to ingest for a mismatched `service_id`.
- **413 Payload Too Large**: Request exceeds the maximum configured batch size (e.g., 5MB).
- **422 Unprocessable Entity**: Malformed JSON, out-of-bounds timestamp (violating T-7 to T+2 policy), or improperly formatted Hex strings.
