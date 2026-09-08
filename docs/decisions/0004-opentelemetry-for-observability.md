# ADR 0004: OpenTelemetry Standard

## Context
We need a standardized format for logs, metrics, and traces to prevent vendor lock-in and simplify ingestion.

## Decision
Adopt OpenTelemetry (OTel) structures for all incoming telemetry payloads.

## Alternatives
- Custom JSON schemas: Leads to fragmentation and incompatibility with standard agents.
- Datadog/NewRelic agents: Proprietary formats.

## Consequences
Ensures future-proofing. We can later easily plug in standard OTel collectors to forward data to our ingest endpoint.
