# ADR 0005: REST API

## Context
The frontend SPA needs to communicate with the FastAPI backend.

## Decision
Use standard REST API conventions with JSON over HTTP.

## Alternatives
- GraphQL: Excellent for flexible queries, but adds complexity and learning curve for MVP.
- gRPC: Great for service-to-service, but overkill for a Next.js frontend SPA.

## Consequences
Standard, easily documentable (OpenAPI/Swagger built into FastAPI), and widely understood by all engineers.
