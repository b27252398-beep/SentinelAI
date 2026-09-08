# Database Architecture

SentinelAI uses PostgreSQL as its primary relational store.

## Entities and Schema

### Users and Access
- **`users`**: `id` (UUID, PK), `email` (String, Unique), `password_hash` (String), `created_at` (Timestamp), `is_active` (Boolean).
- **`roles`**: `id` (UUID, PK), `name` (String, Unique, e.g., 'Engineer').
- **`user_roles`**: `user_id` (UUID, FK), `role_id` (UUID, FK). Composite PK.

### Service Registry
- **`services`**: `id` (UUID, PK), `name` (String, Unique), `repository_url` (String), `owner_id` (UUID, FK to users), `created_at` (Timestamp).

### Incidents and Telemetry
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
- **Data Retention & Indexes**: Raw telemetry data has a default retention of 7 days (configurable) and relies on timestamp indexes for fast deletion and time-window queries. `investigation_evidence` stores independent, persistent copies of the specific telemetry used to form a hypothesis, ensuring that raw telemetry cleanup does not destroy investigation records.
