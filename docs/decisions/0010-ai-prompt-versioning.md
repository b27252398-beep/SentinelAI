# ADR 0010: AI Prompt Versioning

## Context
Prompts dictate the behavior of the AI module. We must ensure that AI decisions are auditable, reproducible, and protected against silent tampering.

## Decision
1. AI prompt templates will be stored as version-controlled files in the Git repository. We will **not** build a database-backed prompt management system for the MVP.
2. Every execution of an AI investigation will explicitly record the `prompt_version` (e.g., the commit hash or a version string) and the `model_identifier` (e.g., `gpt-4-turbo-2024-04-09`) inside the `investigations` database table.

## Alternatives
- Database-backed prompt management: Adds significant UI/API complexity and bypasses standard Git PR review processes for prompt changes.
- Not tracking versions: Makes it impossible to audit why an AI made a specific recommendation in the past if the prompt or model has since changed.

## Consequences
- Prompt updates require a codebase deployment, which is acceptable and preferred for MVP stability.
- Ensures all prompt changes are peer-reviewed.
- Guarantees historical traceability of AI outputs.
