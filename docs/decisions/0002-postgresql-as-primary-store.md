# ADR 0002: PostgreSQL as Primary Store

## Context
We need to store relational data (users, incidents) alongside semi-structured data (raw telemetry, JSON AI outputs).

## Decision
Use PostgreSQL for all primary data storage, utilizing its `JSONB` column types for unstructured telemetry or AI outputs.

## Alternatives
- MongoDB: Good for unstructured, but weak for enforcing strict relationships (users -> roles -> incidents).
- ElasticSearch: Great for logs, but overkill for MVP and hard to manage alongside a relational DB for users.

## Consequences
A single robust database to manage. We may need to migrate raw telemetry to a dedicated time-series DB if scale demands it in later phases.
