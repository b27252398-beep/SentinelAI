# Database Architecture

SentinelAI uses PostgreSQL as its primary relational store.

## Entities and Schema

### Users and Access
- **`users`**: `id` (UUID, PK), `email` (String, Unique), `password_hash` (String), `created_at` (Timestamp), `is_active` (Boolean).
- **`roles`**: `id` (UUID, PK), `name` (String, Unique, e.g., 'Engineer').
- **`user_roles`**: `user_id` (UUID, FK), `role_id` (UUID, FK). Composite PK.

### Service Registry
- **`services`**: `id` (UUID, PK), `name` (VARCHAR(100), NOT NULL), `description` (VARCHAR(255), Optional), `environment` (VARCHAR(50), NOT NULL), `owner_team` (VARCHAR(100), Optional), `is_active` (Boolean, NOT NULL, Default True), `created_at` (TIMESTAMPTZ, NOT NULL), `updated_at` (TIMESTAMPTZ, NOT NULL).
  - *Constraints*: `UNIQUE(name, environment)`.
  - *Indexes*: Appropriate indexes for fast lookup (e.g., on name, environment, is_active).
  *(Note: For the MVP, service ownership is represented as a simple optional owner/team string rather than a rigid Foreign Key to a specific human user account. No separate Team or Environment tables are used. Soft deletion via `is_active` preserves telemetry and incident referential integrity.)*

### Telemetry Ingestion Credentials
- **`machine_credentials`**: `id` (UUID, PK), `service_id` (UUID, Nullable FK), `key_prefix` (VARCHAR(16), Unique, NOT NULL), `api_key_hash` (VARCHAR(64), NOT NULL), `name` (VARCHAR(100), NOT NULL), `is_active` (Boolean, NOT NULL, Default True), `created_at` (TIMESTAMPTZ, NOT NULL), `revoked_at` (TIMESTAMPTZ, Optional).
  *(Note: Used strictly for machine-to-machine telemetry ingestion authentication. Uses prefix-based fast lookup and SHA-256 for secret verification. If service_id is NULL, it acts as a global collector key.)*

### Incidents and Telemetry
- **`telemetry`**: `id` (UUID, Part of PK), `timestamp` (TIMESTAMPTZ, Partition Key & Part of PK), `service_id` (UUID, NOT NULL), `ingestion_timestamp` (TIMESTAMPTZ, NOT NULL), `telemetry_type` (VARCHAR(20), NOT NULL), `trace_id` (VARCHAR(32), Optional OTel ID), `span_id` (VARCHAR(16), Optional OTel ID), `parent_span_id` (VARCHAR(16), Optional OTel ID), `severity_number` (INTEGER, Optional), `metric_name` (VARCHAR(255), Optional), `metric_value` (DOUBLE PRECISION, Optional), `unit` (VARCHAR(50), Optional), `fingerprint` (VARCHAR(64), NOT NULL), `resource_attributes` (JSONB), `event_attributes` (JSONB), `raw_payload` (JSONB, NOT NULL).
  *(Constraints: `PRIMARY KEY (id, timestamp)`, `UNIQUE (fingerprint, timestamp)`. Note: Explicit Database Foreign Keys are NOT used from long-lived tables to `telemetry` due to partitions dropping after 7 days.)*
- **`incidents`**: `id` (UUID, PK), `title` (String), `status` (String/Enum: open, investigating, resolved), `severity` (String/Enum: P1-P4), `service_id` (UUID, FK), `assigned_to` (UUID, Nullable FK), `created_at` (Timestamp), `resolved_at` (Nullable Timestamp).
- **`incident_events`**: `id` (UUID, PK), `incident_id` (UUID, FK), `event_type` (String), `description` (Text), `timestamp` (Timestamp).
- **`anomalies`**: `id` (UUID, PK), `service_id` (UUID, FK), `metric_name` (String), `score` (Float), `timestamp` (Timestamp), `incident_id` (UUID, Nullable FK).

### AI Investigation
- **`investigations`**: `id` (UUID, PK), `incident_id` (UUID, FK), `status` (String/Enum: pending, running, complete, failed), `prompt_version` (String), `model_identifier` (String), `started_at` (Timestamp), `completed_at` (Nullable Timestamp).
- **`investigation_evidence`**: `id` (UUID, PK), `investigation_id` (UUID, FK), `evidence_type` (String: log/metric/trace), `raw_data` (JSONB), `source_timestamp` (Timestamp). Represents OBSERVED FACTS.
- **`hypotheses`**: `id` (UUID, PK), `investigation_id` (UUID, FK), `description` (Text), `confidence_score` (Integer 0-100), `is_root_cause` (Boolean). Represents INFERENCES.
- **`recommendations`**: `id` (UUID, PK), `hypothesis_id` (UUID, FK), `action_description` (Text), `risk_level` (String: low/medium/high).
- **`recommendation_decisions`**: `id` (UUID, PK), `recommendation_id` (UUID, FK), `decision` (String/Enum: approved, rejected), `decided_by` (UUID, FK to users), `rationale` (Text), `timestamp` (Timestamp).

### Audit
- **`audit_logs`**: `id` (UUID, PK), `user_id` (UUID, Nullable FK), `action` (String), `resource_type` (String), `resource_id` (UUID), `details` (JSONB), `timestamp` (Timestamp). (Append-only).

## Technical Considerations
- **UUIDs**: All primary keys use UUIDv4.
- **Timestamps**: All tables include UTC timestamps.
- **Soft Deletion**: `services` and `users` use `is_active` flags instead of hard deletes to maintain audit integrity.
- **Data Retention & Partitioning**: The `telemetry` table utilizes PostgreSQL time-based partitioning (e.g., daily partitions). Raw telemetry has a default retention of 7 days (configurable). Cleanup is handled efficiently by dropping old partitions. `investigation_evidence` stores independent, persistent copies of the specific telemetry payloads used to form a hypothesis, ensuring that dropping raw telemetry partitions does not destroy long-term investigation records.
