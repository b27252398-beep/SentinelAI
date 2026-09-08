# 11. Primary Key Strategy

Date: 2026-09-08

## Status

Accepted

## Context

During Phase 2C, the authentication and RBAC foundation was implemented using standard auto-incrementing `Integer` primary keys in SQLAlchemy. However, the original `DATABASE_ERD.md` and `DATABASE_ARCHITECTURE.md` established `UUID` as the primary key standard for the entire platform.

SentinelAI relies heavily on telemetry correlation, distributed observability ingestion, and secure incident management. We need to decide whether to adopt UUIDs consistently across all tables (including Auth) or revert to Integers.

## Decision

We will use **UUIDs (UUIDv7 or UUIDv4 fallback)** as the primary key type for all database tables across the platform, including the `users`, `roles`, and `permissions` tables implemented in Phase 2C.

## Rationale

While integer IDs are technically highly scalable and performant for database indexing, UUIDs (specifically UUIDv4 or UUIDv7) are preferred for the SentinelAI architecture because they provide:
- Opaque externally exposed identifiers, preventing resource enumeration.
- Non-sequential resource identifiers.
- Decentralized and client-side generation without synchronous database round-trips.
- Native compatibility with future distributed ingestion from OpenTelemetry agents.
- Consistent identifiers across all SentinelAI domain entities.

*Important Distinction*: SentinelAI domain entity IDs (Users, Services, Incidents) use UUIDs. OpenTelemetry identifiers (TraceId, SpanId) are conceptually distinct from internal domain UUIDs. OpenTelemetry identifiers are strict 128-bit/64-bit Hex Strings and will be stored as such, independently of the primary key strategy chosen for SentinelAI domain models.

## Alternatives Considered

- **Integers**: Natively supported by SQLAlchemy defaults. Rejected because enumeration is a security concern for this platform and it impedes offline identifier generation.
- **Integers Internally, UUIDs Externally**: Adds unnecessary translation complexity to the API layer for the MVP.

## Consequences

- The existing Phase 2C SQLAlchemy models (`User`, `Role`, `Permission`) must be updated to use `UUID`.
- Pydantic schemas must be updated to accept and serialize `UUID` instead of `int`.

## Migration Strategy

Because Phase 2C (which uses integer IDs) has already been committed to Git, but the database contains no production data, we evaluate the following approaches to migrate the schema:

- **Option A: Controlled table recreation / migration with UUID columns.** Create a new forward-only Alembic revision that drops the existing Phase 2C tables and recreates them (or explicitly `ALTER`s columns) using UUIDs.
- **Option B: Rebuild development database from corrected migration history.** Modify the committed Alembic script `a13262d578ec_add_auth_models.py` in-place, and require all developers to drop and recreate their local databases.
- **Option C: Compatibility migration.** Write a complex migration that explicitly casts the integer IDs to UUIDs to preserve data.

**Recommendation**: **Option A** is the safest approach. Although Option B is tempting for a local MVP, modifying committed Git history (the existing migration file) is bad practice. Option A respects the immutable Phase 2C Git history by appending a new forward-only migration that explicitly drops and recreates the authentication tables with UUIDs. Since there is no production data, data loss during this recreation is irrelevant, making Option A both clean and safe.
