# REST API Specification

The SentinelAI API follows RESTful conventions and uses JSON. All endpoints require a valid JWT `Authorization: Bearer <token>` header except `/auth/login`.

## Authentication
- **`POST /api/v1/auth/login`**: Authenticates user and returns JWT.

## Users & Roles
- **`GET /api/v1/users`** [Admin]: Lists users.
- **`POST /api/v1/users`** [Admin]: Creates a user.
- **`GET /api/v1/roles`** [Admin]: Lists available roles.

## Services
- **`GET /api/v1/services`** [Viewer+]: Lists services.
- **`POST /api/v1/services`** [Admin, Manager]: Registers a service.

## Telemetry
- **`POST /api/v1/telemetry/ingest`** [System]: Accepts OTLP-like JSON payload for logs, metrics, or traces.

## Incidents
- **`GET /api/v1/incidents`** [Viewer+]: Lists incidents (filterable by status/severity).
- **`POST /api/v1/incidents`** [Manager, System]: Creates an incident.
- **`GET /api/v1/incidents/{id}`** [Viewer+]: Gets incident details.
- **`PATCH /api/v1/incidents/{id}`** [Manager, Engineer]: Updates status, severity, or assignment.

## Anomalies & Correlations
- **`GET /api/v1/anomalies`** [Viewer+]: Lists detected anomalies.
- **`GET /api/v1/incidents/{id}/correlations`** [Viewer+]: Gets events and anomalies temporally correlated with the incident.

## Investigations & AI
- **`POST /api/v1/incidents/{id}/investigations`** [Engineer, Manager]: Triggers a new AI investigation.
- **`GET /api/v1/investigations/{id}`** [Viewer+]: Gets investigation status.
- **`GET /api/v1/investigations/{id}/evidence`** [Viewer+]: Gets OBSERVED facts retrieved for the investigation.
- **`GET /api/v1/investigations/{id}/hypotheses`** [Viewer+]: Gets AI-generated inferences/root causes.
- **`GET /api/v1/investigations/{id}/recommendations`** [Viewer+]: Gets actionable remediation steps.

## Approvals
- **`POST /api/v1/recommendations/{id}/approve`** [Manager]: Approves a recommendation.
- **`POST /api/v1/recommendations/{id}/reject`** [Manager]: Rejects a recommendation with rationale.

## Audit Logs
- **`GET /api/v1/audit-logs`** [Admin]: Fetches system audit logs.
