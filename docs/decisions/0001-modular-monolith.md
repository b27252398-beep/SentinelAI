# ADR 0001: Modular Monolith Architecture

## Context
SentinelAI involves many distinct domains (auth, telemetry, AI, anomaly detection). There is a temptation to start with microservices to reflect this domain separation.

## Decision
We will build SentinelAI as a modular monolith in Python (FastAPI). 

## Alternatives
- Microservices: Too complex for MVP, requires heavy orchestration.
- Serverless: Hard to run long background LLM tasks reliably within strict timeout windows.

## Consequences
Simplifies local development, deployment, and testing during Phase 1. Requires strict discipline to avoid tight coupling between internal modules.
