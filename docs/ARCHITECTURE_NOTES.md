# Architecture Notes

## Initial Architectural Principles
- **Modular Monolith**: We will start with a modular monolith to avoid premature microservice complexities while retaining strong internal boundaries.
- **Evidence-Based AI**: The AI must strictly differentiate between observed facts (directly retrieved system data), inferences (conclusions derived from evidence), and recommendations. It must not present unsupported assumptions as facts.
- **Safety First**: No autonomous destructive actions. Remediation always requires human approval.

## Major System Boundaries
The conceptual backend modules within the monolith include:
- `auth/`: User authentication and authorization.
- `users/`: User management and profiles.
- `services/`: Service registry and metadata.
- `telemetry/`: Ingestion and storage of logs, metrics, and traces.
- `incidents/`: Incident lifecycle management.
- `anomaly/`: Statistical and AI-driven anomaly detection.
- `correlation/`: Event temporal and spatial correlation logic.
- `investigation/`: Core workflow for orchestrating investigations and gathering evidence.
- `recommendations/`: Generation and approval of remediation plans.
- `audit/`: Action tracking for compliance.
- `ai/`: Integration with LLMs, prompt management, and response parsing.

## Technology Decisions
- **Frontend**: Next.js, TypeScript, modern responsive dashboard UI.
- **Backend**: Python, FastAPI.
- **Database**: PostgreSQL (relational store for users, services, incidents, audit logs, and metadata).
- **Caching/Background Processing**: Redis (for task queues, rate limiting, temporary caching).
- **Observability**: OpenTelemetry (standardizing telemetry ingestion).
- **AI**: LLM-based layer for investigation, combined with conventional statistical methods for anomaly detection.
- **Infrastructure**: Docker, Docker Compose (for local development/MVP), GitHub Actions (CI/CD).
- **Testing**: Pytest (Python backend), Playwright (E2E), TypeScript/ESLint (Frontend).

## Important Assumptions
- **Simulated Environment**: Development will leverage a controlled simulated production environment with services like api-gateway, user-service, etc. Known failure scenarios (e.g., memory leaks, database exhaustion) will be injected for testing.
- **Telemetry Source**: Telemetry data will be pre-formatted or normalized during ingestion to align with OpenTelemetry standards.
