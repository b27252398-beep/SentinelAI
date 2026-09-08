# Database Architecture

SentinelAI uses PostgreSQL as its primary relational store.

## Entities and Schema

### Users and Access
- **`users`**: `id` (UUID, PK), `email` (String, Unique), `password_hash` (String), `created_at` (Timestamp), `is_active` (Boolean).
- **`roles`**: `id` (UUID, PK), `name` (String, Unique, e.g., 'Engineer').
- **`user_roles`**: `user_id` (UUID, FK), `role_id` (UUID, FK). Composite PK.

### Service Registry
- **`services`**: `id` (UUID, PK), `name` (String, Unique), `repository_url` (String), `owner_team` (String, Optional), `created_at` (Timestamp).
  *(Note: For the MVP, service ownership is represented as a simple optional owner/team string rather than a rigid Foreign Key to a specific human user account. This prevents lifecycle complexity—such as what happens to a service when its single human owner leaves the company or is deactivated—and aligns better with real-world DevOps practices where teams, not individuals, own services.)*

### Incidents and Telemetry
- **`telemetry`**: `id` (UUID, PK), `service_id` (UUID, FK), `timestamp` (Timestamp), `ingestion_timestamp` (Timestamp), `telemetry_type` (String/Enum: log, metric, trace), `trace_id` (String, Optional 128-bit OTel ID), `span_id` (String, Optional 64-bit OTel ID), `parent_span_id` (String, Optional 64-bit OTel ID), `severity` (String, Optional), `resource_attributes` (JSONB), `event_attributes` (JSONB), `raw_payload` (JSONB).
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
