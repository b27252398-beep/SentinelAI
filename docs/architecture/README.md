# SentinelAI Architecture Documentation

Welcome to the SentinelAI Architecture index. This repository of documents details the design of the Phase 1 MVP.

## Architecture Overview
SentinelAI is an AI-assisted software incident detection platform. It uses a **Modular Monolith** architecture, a Next.js frontend, a FastAPI backend, PostgreSQL for persistence, and Redis for asynchronous task processing.

## Architecture Documents

### System & High-Level Design
- [System Architecture](SYSTEM_ARCHITECTURE.md): C4 diagrams, data flows, and trust boundaries.
- [Backend Architecture](BACKEND_ARCHITECTURE.md): FastAPI module boundaries.
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md): Next.js structure and UI domains.

### Data & API
- [Database Architecture](DATABASE_ARCHITECTURE.md): Schema design and entities.
- [Database ERD](DATABASE_ERD.md): Entity-Relationship Diagram.
- [API Specification](API_SPECIFICATION.md): REST endpoints and access control.

### Core Domain Workflows
- [Telemetry Architecture](TELEMETRY_ARCHITECTURE.md): OTel ingestion strategy.
- [Detection & Correlation](DETECTION_CORRELATION.md): Statistical anomaly pipeline.
- [AI Investigation](AI_INVESTIGATION.md): Evidence-backed LLM workflow.
- [Investigation Data Model](INVESTIGATION_MODEL.md): Lifecycle of an investigation.
- [Recommendation Workflow](RECOMMENDATION_WORKFLOW.md): Human-in-the-loop approval process.

### Security, Testing & Ops
- [Auth & RBAC](AUTH_RBAC.md): Roles, permissions, and JWT strategy.
- [Threat Model](THREAT_MODEL.md): Vulnerability mitigation.
- [Testing Architecture](TESTING_ARCHITECTURE.md): Test layers and evaluation metrics.
- [Deployment Architecture](DEPLOYMENT_ARCHITECTURE.md): Docker Compose local environment.

## Architecture Decision Records (ADRs)
Major decisions are documented in the `../decisions/` directory:
- [ADR 0001: Modular Monolith](../decisions/0001-modular-monolith.md)
- [ADR 0002: PostgreSQL as Primary Store](../decisions/0002-postgresql-as-primary-store.md)
- [ADR 0003: Redis for Async Workers](../decisions/0003-redis-for-async-and-caching.md)
- [ADR 0004: OpenTelemetry Standard](../decisions/0004-opentelemetry-for-observability.md)
- [ADR 0005: REST API](../decisions/0005-rest-api-architecture.md)
- [ADR 0006: Human-in-the-Loop AI](../decisions/0006-human-in-the-loop-ai.md)
- [ADR 0007: Conventional Detection + LLM](../decisions/0007-hybrid-detection-llm.md)
- [ADR 0008: Simulated Production Environment](../decisions/0008-simulated-production-environment.md)
- [ADR 0009: Telemetry Retention](../decisions/0009-telemetry-retention.md)
- [ADR 0010: AI Prompt Versioning](../decisions/0010-ai-prompt-versioning.md)

## Implementation Sequence
1. Setup Docker Compose base infrastructure (DB, Redis).
2. Scaffold FastAPI backend and core database migrations.
3. Implement Auth & RBAC modules.
4. Implement Service & Telemetry ingestion.
5. Scaffold Next.js frontend and dashboard UI.
6. Implement Anomaly Detection workers.
7. Implement Incident & Event Correlation.
8. Integrate LLM and Investigation workflow.
9. Implement Recommendation approval UI.
