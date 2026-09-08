# ADR 0006: Human-in-the-Loop AI

## Context
AI can hallucinate or suggest destructive infrastructure changes.

## Decision
The AI will generate Root Causes and Recommendations, but an `Incident Manager` must explicitly approve any recommendation. The AI cannot execute actions autonomously.

## Alternatives
- Fully Autonomous: Too dangerous for production systems.
- Purely Informational: Limits the value proposition if the AI doesn't at least propose a concrete fix.

## Consequences
Ensures safety and builds trust with engineers. Requires building a dedicated approval UI and audit trail.
