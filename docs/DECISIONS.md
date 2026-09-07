# Architecture Decision Records (ADR)

## ADR 1: Use of a Modular Monolith over Microservices
**Date**: 2026-09-08
**Status**: Accepted

### Context
SentinelAI involves many distinct domains (auth, telemetry, AI, anomaly detection). There is a temptation to start with microservices to reflect this domain separation.

### Decision
We will build SentinelAI as a modular monolith in Python (FastAPI). 

### Consequences
- **Positive**: Simplifies local development, deployment, and testing during Phase 1. Reduces operational overhead and cross-service communication complexities.
- **Negative**: Requires strict discipline to avoid tight coupling between modules (e.g., `auth` should not directly depend on `anomaly`).
- **Mitigation**: We will enforce strict module boundaries using directory structures and dependency rules.

## ADR 2: Strict AI Output Categorization
**Date**: 2026-09-08
**Status**: Accepted

### Context
Using LLMs for root-cause analysis can lead to "hallucinations" where the AI presents guesses as facts, which is dangerous for production incident resolution.

### Decision
The AI investigation layer will enforce a strict structured output requirement. All AI responses must separate:
1. **Observed Fact**: Directly measured system evidence.
2. **Inference**: A conclusion derived from evidence.
3. **Recommendation**: A proposed action.

### Consequences
- **Positive**: Increases engineer trust in the platform. Allows safe review of recommendations.
- **Negative**: Increases prompt complexity and requires more sophisticated parsing logic.
