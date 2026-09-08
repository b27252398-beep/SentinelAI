# ADR 0008: Simulated Production Environment

## Context
We need telemetry data to test detection and AI RCA, but we don't have a real production environment generating traffic.

## Decision
Build a Python script/container that simulates microservice traffic and periodically injects known failure scenarios (e.g., DB connection exhaustion).

## Alternatives
- Static datasets: Hard to test real-time ingestion and correlation.
- Deploying a real microservices demo (like Google microservices-demo): Too heavy, hard to reliably trigger specific edge-case failures.

## Consequences
Gives us a controlled ground-truth to measure AI accuracy (Precision, Recall, Top-1 Accuracy) against known injected faults.
