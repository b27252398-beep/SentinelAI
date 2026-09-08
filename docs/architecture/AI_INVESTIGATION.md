# AI Investigation Architecture

The core value proposition of SentinelAI is its AI-assisted Root Cause Analysis (RCA).

## AI Pipeline
1. **Investigation Planner**: Receives the Incident and Correlated Events.
2. **Evidence Retriever**: Queries the database for raw logs/metrics related to the events.
3. **Hypothesis Engine**: LLM analyzes the evidence and generates potential root causes.
4. **Evidence Evaluator**: LLM scores hypotheses based strictly on the retrieved evidence.
5. **Recommendation Engine**: Proposes remediation steps for the top-ranked hypothesis.

## Strict Output Categorization
The LLM must output strictly typed JSON (enforced via Pydantic schemas in FastAPI and OpenAI Structured Outputs if applicable).
- **OBSERVED**: The raw data (e.g., Log: "DB Connection Timeout").
- **INFERRED**: The AI's logical deduction (e.g., "The DB connection pool was exhausted, causing the API gateway to queue requests").
- **RECOMMENDATION**: The action (e.g., "Increase DB pool size").

## Hallucination Controls
- **Zero-Shot Prompting with Grounding**: The LLM prompt explicitly states: *"You may only use the provided telemetry data. Do not invent external causes. If the data is insufficient, state 'Insufficient Evidence'."*
- **Temperature**: Set to `0.0` or `0.1` for deterministic, analytical responses.
- **Evidence Linking**: Every generated hypothesis must include an array of `evidence_ids` referencing the exact raw telemetry records that support it. The system must verify these IDs exist.

## Prompt Versioning & Reproducibility
- **Version Control**: AI prompt templates are stored as version-controlled text files in the codebase, NOT in a database-backed prompt management system. All changes to prompts go through standard Git PR reviews.
- **Traceability**: Every AI investigation records the `prompt_version` (e.g., Git commit hash or internal version string) and the `model_identifier` (e.g., `gpt-4-turbo-2024-04-09`) in the `investigations` table.
- **Auditability**: These records ensure that historical AI recommendations are fully traceable and reproducible relative to the model's capabilities at the time.

## Human Review
The AI operates asynchronously. It writes its findings to the database. Engineers review the findings on the dashboard. The AI does **NOT** auto-resolve incidents or execute infrastructure changes.
