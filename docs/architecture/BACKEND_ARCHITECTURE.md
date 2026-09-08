# Backend Architecture

The backend is a **Python FastAPI Modular Monolith**. It is divided into strictly isolated logical modules. Modules communicate via internal Python interfaces, never through HTTP.

## Module Definitions

### 1. auth
- **Responsibility**: User login, JWT generation, session validation.
- **Inputs**: Credentials (email, password).
- **Outputs**: JWT tokens.
- **Dependencies**: `users` module (for credential validation).
- **Security**: Password hashing (Argon2/Bcrypt).

### 2. users
- **Responsibility**: User and role management.
- **API**: CRUD for users and roles.
- **Database**: `users`, `roles`, `user_roles` tables.
- **Dependencies**: None.

### 3. services
- **Responsibility**: Service registry (environment, version, repository).
- **API**: CRUD for services.
- **Database**: `services` table.

### 4. telemetry
- **Responsibility**: Ingestion, normalization, and querying of logs, metrics, traces.
- **Dependencies**: `services` (to map telemetry to registered services).

### 5. incidents
- **Responsibility**: Core incident lifecycle (creation, status updates, assignment).
- **Outputs**: Triggers for correlation/investigation.
- **Database**: `incidents`, `incident_events` tables.

### 6. anomaly
- **Responsibility**: Statistical evaluation of telemetry to detect deviations.
- **Inputs**: Data from `telemetry`.
- **Outputs**: Creates records in `anomalies` table.
- **Async**: Heavy calculations run via Redis queues.

### 7. correlation
- **Responsibility**: Groups anomalies and telemetry into cohesive incidents.
- **Inputs**: `anomalies`, `telemetry`.
- **Outputs**: Correlated `incidents`.

### 8. investigation
- **Responsibility**: Orchestrates the evidence-gathering and AI workflow.
- **Dependencies**: `ai`, `telemetry`, `incidents`.

### 9. recommendations
- **Responsibility**: Manages proposed remediations and human approvals.
- **Database**: `recommendations`, `recommendation_decisions` tables.

### 10. audit
- **Responsibility**: Tamper-evident logging of all state-changing actions.
- **Dependencies**: None. Cross-cutting concern utilized by all other modules.

### 11. ai
- **Responsibility**: Interfacing with LLMs, prompt management, parsing structured JSON outputs, and enforcing the Fact/Inference/Recommendation boundaries.
- **Outputs**: Strongly typed Pydantic models separating inferences from facts.
