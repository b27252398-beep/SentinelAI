# Detection and Correlation Architecture

## 1. Detection Pipeline Flow
The subsystem enforces strict isolation between telemetry ingestion and intelligence inference. 
The immediate boundary pipeline is:
`Telemetry → Feature Extraction (Rolling Window) → Detection Engine → Anomaly Event → Severity Assignment`
*(Future)*: `Anomaly Event → Correlation Engine → Incident`

## 2. Worker Architecture and Coordination
Anomaly detection executes asynchronously to protect API ingestion latency.
- **Dedicated Detection Worker**: A standalone Python process (e.g., `python -m app.detection.worker`) operating within the modular monolith deployment.
- **Redis Coordination**: Uses Redis distributed locks (`SET lock:detection:{service_id}:{window_start} NX EX 60`) to enforce mutual exclusion (at-most-one concurrent execution per window per service). Heavy queues (Kafka, Celery) are explicitly rejected.
- **Independence**: The worker operates independently from FastAPI web processes.

## 3. Execution Guarantee & Idempotency Semantics
- **At-Most-One Concurrent Execution**: The Redis lock prevents simultaneous evaluation. It does NOT guarantee strict exactly-once processing (if a worker crashes before committing, the lock expires).
- **Idempotency Strategy**: The system relies on database uniqueness. A retry explicitly utilizes PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` targeting the exact anomaly identity tuple `(service_id, detector_config_id, config_version, feature, window_start)`. This safely absorbs retries without generating duplicate anomalies.

## 4. Detector Strategy
- **Level 1 (MVP)**: *Static Thresholds*. Deterministic, highly explainable limits.
- **Level 2 (MVP)**: *Statistical Baseline (Z-Score)*. Dynamically identifies deviations relative to a rolling baseline using mean and standard deviation.
- **Level 3 (Deferred)**: *Isolation Forest / Multivariate ML*. Excluded from MVP to prevent cold-start delays.

## 5. Window Semantics
- **Fixed Window Size**: The MVP permanently locks aggregation windows to exactly 5 minutes (300 seconds).
- **Bucket Boundaries**: Timestamps are floored to the nearest 5-minute interval (e.g., `10:00:00` to `10:04:59.999`).

## 6. Feature and Raw-Sample Semantics
- **Raw Telemetry Samples**: The individual JSON records ingested into Postgres.
- **Feature Extraction**: The mathematical aggregation executed across the raw samples within a 5-minute bucket.
- **Minimum Raw Samples (`min_raw_samples`)**: Defines the absolute minimum database telemetry events physically required within a 5-minute bucket to compute a reliable aggregation feature.

## 7. Baseline Semantics
- **Rolling Baseline**: Composed of the previous twelve 5-minute windows (1 hour).
- **Minimum Baseline Observations (`min_baseline_observations`)**: The minimum number of valid (non-NULL) historical 5-minute windows required to compute a Z-score (e.g., 10 out of 12). If unmet, the detector fails safe, evaluates to "Undetermined", and skips.

## 8. Missing Data Semantics
A lack of specific events does NOT universally imply zero.
- **Observed Zero**: For count/rate metrics, zero is ONLY yielded if global telemetry confirms the service is alive. Specifically: if total spans/metrics received for the service in the window > 0, but the target subset (e.g., 5xx spans) is zero, the feature yields an explicit `0.0`.
- **Missing Observation**: Occurs if NO telemetry is received for the service in the window whatsoever, OR when evaluating distributions (e.g., latency, CPU) where zero is mathematically invalid. Evaluates to `NULL` and is excluded from statistical baselines.

## 9. Numerical Edge Case Handling (Z-Score)
- **Mathematical Precision**: The Z-score is strictly defined as `z = (observed_value - baseline_mean) / max(baseline_stddev, 0.0001)`.
- **NaN / Infinity**: Rejected at the extraction layer. Non-finite results automatically convert the feature to a Missing Observation (`NULL`).

## 10. Anomaly Identity & Schema
**Table: `anomaly_events`**
The persisted anomaly model natively includes configuration identities to enforce deterministic idempotency and historical reproduction:
- `id`: UUID PRIMARY KEY
- `service_id`: UUID
- `detector_config_id`: UUID
- `config_version`: INTEGER
- `detector_type`: VARCHAR
- `feature`: VARCHAR
- `window_start`: TIMESTAMPTZ
- `window_end`: TIMESTAMPTZ
- `severity`: VARCHAR
- `status`: VARCHAR (OPEN, RESOLVED)
- `cooldown_count`: INTEGER
- `evidence`: JSONB

**Idempotency Identity**: The PostgreSQL `UNIQUE` constraint strictly targets `(service_id, detector_config_id, config_version, feature, window_start)` ensuring anomaly state merges safely during retried execution.

## 11. Configuration Versioning & Schema
**Table: `detector_configs`**
- `id`: UUID PRIMARY KEY
- `service_id`: UUID
- `detector_type`: VARCHAR
- `feature`: VARCHAR
- `enabled`: BOOLEAN
- `aggregation_function`: VARCHAR
- `min_raw_samples`: INTEGER
- `min_baseline_observations`: INTEGER
- `cooldown_windows`: INTEGER
- `config`: JSONB (Contains the operational constants for reproduction)
  - *STATIC_THRESHOLD example*: `{"warning_threshold": 90.0, "critical_threshold": 95.0, "operator": ">="}`
  - *Z_SCORE example*: `{"warning_z": 4.0, "critical_z": 5.0}`
- `version`: INTEGER
- `created_at` / `updated_at`: TIMESTAMPTZ

**Versioning Strategy**: A detector configuration version is strictly **immutable**. 
The uniqueness constraint is `UNIQUE(service_id, feature, detector_type, version)`. Changing detector parameters inserts a NEW configuration row with an incremented `version`. Historical versions remain persisted. Old anomaly events retain the `config_version` that generated them, mathematically guaranteeing historical reproducibility and preventing accidental modification of established detection logic.

## 12. Severity Algorithm
**Anomaly Severity** represents the pure mathematical intensity of the deviation. This explicitly represents **ANOMALY SEVERITY**, not INCIDENT SEVERITY. Incident severity remains a future correlation/business-impact concern.
- **P4 (Low)**: Z-score >= 3
- **P3 (Medium)**: Z-score >= 4 OR static warning threshold breached
- **P2 (High)**: Z-score >= 5 OR static critical threshold breached
- **P1 (Critical)**: 3 consecutive P2 breaches
- **Precedence**: When multiple conditions apply, the highest severity wins (P1 > P2 > P3 > P4).

## 13. Anomaly Lifecycle (State Machine)
The lifecycle strictly manages states: `OPEN` and `RESOLVED`.
1. **Creation**: An anomalous window generates an `OPEN` event with `cooldown_count = 0`.
2. **Extension**: A repeated anomalous window matching the identity extends `window_end`, updates `evidence` (highest deviation peak), and resets `cooldown_count = 0`.
3. **Cooldown**: A valid "clean window" (value does not breach thresholds) does NOT resolve the anomaly. It leaves `window_end` unchanged and increments the `cooldown_count` field.
4. **Interrupted Cooldown**: If an anomalous window occurs during cooldown (e.g., `cooldown_count == 1`), `cooldown_count` instantly resets to `0` and `window_end` extends.
5. **Resolution**: The exact transition to `RESOLVED` occurs when `cooldown_count >= cooldown_windows` (e.g., after 2 consecutive clean windows).
6. **Post-Resolution**: Once `RESOLVED`, the anomaly is permanently closed. Any subsequent breach generates an entirely new `OPEN` anomaly.
7. **Execution Failure**: A detector crash skips the window. It is distinctly NOT a clean window, so `cooldown_count` is not incremented.

## 14. Worker Security Model
The Detection Worker strictly follows least privilege.
- **Capabilities**: Read-only DB access to `telemetry` and `detector_configs`. Read/Write access strictly to `anomaly_events`.
- **Restrictions**: NO API ingress, NO administrative mutation privileges, NO machine token access.

## 15. Failure Scenario Mappings
1. **Database Connection Exhaustion**:
   - Telemetry Signal: `db_connections` metric.
   - Mathematical Formula: `current_connections = avg(metric_value)`
   - Feature: `avg_db_connections`
   - Detector: Static Threshold
   - Anomaly Condition: `current_connections >= configured_critical_threshold`
   - Anomaly Severity: P2
2. **Memory Leak**:
   - Telemetry Signal: `memory_usage` metric.
   - Mathematical Formula: `current_memory = avg(metric_value)`
   - Feature: `avg_memory`
   - Detector: Z-Score
   - Anomaly Condition: `z = (current_memory - baseline_mean) / max(baseline_stddev, 0.0001)` evaluates to `z >= 4.0`
   - Anomaly Severity: P3
3. **API Latency Degradation**:
   - Telemetry Signal: `duration` from spans.
   - Mathematical Formula: `current_latency = percentile_cont(0.95) WITHIN GROUP (ORDER BY duration)`
   - Feature: `p95_latency`
   - Detector: Z-Score
   - Anomaly Condition: `z = (current_latency - baseline_mean) / max(baseline_stddev, 0.0001)` evaluates to `z >= 5.0`
   - Anomaly Severity: P2
4. **Deployment Regression**:
   - Telemetry Signal: HTTP status codes from web spans. **(Technically supported by Telemetry Foundation through the canonical `http_status_code` column).**
   - Mathematical Formula: `current_error_rate = count(spans WHERE http_status_code >= 500) / count(all web spans)`
   - Feature: `error_rate`
   - Detector: Static Threshold
   - Anomaly Condition: `current_error_rate >= 0.01`
   - Anomaly Severity: P3 (Warning) or P2 (Critical)
5. **Dependency Failure**:
   - Telemetry Signal: Explicit outbound traces (`span_kind = CLIENT`). **(Outbound span classification is supported by Telemetry Foundation through the canonical `span_kind` column, but outbound error-status semantics remain a telemetry capability gap)**.
   - Mathematical Formula: `current_error_rate = count(outbound spans with error) / count(all outbound spans)`
   - Feature: `dependency_error_rate`
   - Detector: Z-Score
   - Anomaly Condition: `z = (current_error_rate - baseline_mean) / max(baseline_stddev, 0.0001)` evaluates to `z >= 4.0`
   - Anomaly Severity: P3

*(Correlation Target for all: Future Correlation Engine. Anomalies DO NOT create incidents directly).*

## 16. Evaluation Methodology
Simulated scenarios rely on precise injection to calculate detection efficacy. Detection evaluation remains strictly independent from future incident evaluation.
- **Ground Truth Anomaly Interval**: Absolute timestamp boundary `[t_start, t_end]` of the injected failure.
- **Detection Window**: The fixed 5-minute bucket boundaries `[w_start, w_end)`. A window maps to the ground truth if `w_start >= t_start` and `w_start < t_end`.
- **Detection Timestamp**: The physical wall-clock time the worker executes (e.g., `w_end + 30s`).
- **Detection Latency**: `min(Detection Timestamp) - t_start`. Tracks actual operational MTTI.
- **True Positive (TP)**: The first `OPEN` anomaly intersecting the ground-truth interval counts as ONE True Positive Anomaly Detection. Multiple anomalous windows from one injected failure extend the anomaly event but are counted as a single incident-level True Positive.
- **False Positive (FP)**: An `OPEN` anomaly existing entirely outside any ground-truth interval.
- **False Negative (FN)**: A ground-truth interval that completely elapses without generating an overlapping anomaly event.
- **True Negative (TN)**: Clean detection windows existing outside any ground truth anomaly interval.
- **Precision**: `TP / (TP + FP)`
- **Recall**: `TP / (TP + FN)`
- **F1 Score**: `2 * (Precision * Recall) / (Precision + Recall)`
- **False Positive Rate (FPR)**: `FP / (FP + TN)`

## 17. API Surface
- `GET /api/v1/anomalies`
- `GET /api/v1/anomalies/{id}`
- `GET /api/v1/detectors`
- `POST /api/v1/detectors`

## 18. Architectural Boundaries
- Detection is strictly mathematical. NO LLMs are invoked during the primary detection pipeline.
- The Detection subsystem generates `anomaly_events`. It does NOT synthesize `incidents`. Incident creation is reserved exclusively for the future Event Correlation subsystem.
