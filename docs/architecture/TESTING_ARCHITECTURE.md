# Testing Architecture

SentinelAI mandates a rigorous testing strategy due to the complexity of AI and telemetry processing.

## Testing Layers
1. **Unit Tests** (Pytest): Covers individual Python functions, especially statistical anomaly detection logic and data normalizers.
2. **Integration Tests** (Pytest + Testcontainers): Verifies FastAPI endpoints, PostgreSQL queries, and Redis job queuing.
3. **Frontend Tests** (Jest/React Testing Library): Tests UI components and RBAC conditional rendering.
4. **End-to-End Tests** (Playwright): Simulates the full user journey: login, viewing an incident, triggering an investigation, and approving a recommendation.

## AI and Detection Evaluation Metrics
Using the controlled simulated environment, we inject known failures and measure:

### Detection Metrics
- **Precision**: True anomalies / (True anomalies + False anomalies).
- **Recall**: True anomalies / (True anomalies + Missed anomalies).
- **False-positive rate**: Rate of alerts triggered during normal steady-state operations.

### Root-Cause Analysis (RCA) Metrics
- **Top-1 Accuracy**: Does the primary AI hypothesis match the injected failure?
- **Top-3 Accuracy**: Is the injected failure within the top 3 AI hypotheses?

### AI Trust Metrics
- **Evidence Accuracy**: Percentage of AI-cited `evidence_ids` that actually exist and are relevant.
- **Unsupported-Claim Rate**: Frequency of AI producing an INFERENCE without citing OBSERVED evidence.
- **Prompt Regression**: Because prompts are version-controlled, changes to the prompt template trigger automated evaluations against historic incidents to ensure the `prompt_version` update doesn't degrade Top-1 Accuracy.

### System Metrics
- **MTTI (Mean Time to Identify)**: Time from telemetry ingestion to the engineer receiving an approved recommendation.
- **Investigation Latency**: Time taken for the LLM pipeline to complete.
