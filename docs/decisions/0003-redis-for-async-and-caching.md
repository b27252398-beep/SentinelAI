# ADR 0003: Redis for Async Workers and Caching

## Context
Anomaly detection and LLM API calls are slow and must not block the main API threads.

## Decision
Use Redis as the message broker for background task queues (e.g., Celery or Arq) and as a caching layer.

## Alternatives
- RabbitMQ: Too heavy/complex for simple MVP queues.
- In-memory Python queues: Lost on server restart, cannot scale horizontally.

## Consequences
Fast, reliable background job processing. Adds Redis to the required infrastructure stack.
