# Recommendation and Human Approval Workflow

## Goal
Provide actionable remediation steps based on the AI's root-cause analysis, ensuring no destructive actions are executed without human oversight.

## Workflow
1. **Recommendation Generation**: The AI generates recommendations linked to the primary root cause.
2. **Attributes**:
   - `action_description`: The specific fix (e.g., "Roll back user-service to v1.2.3").
   - `risk_level`: Estimated risk of the action (Low/Medium/High).
   - `confidence`: AI's confidence in this fix solving the root cause.
3. **Approval Process**:
   - An `Incident Manager` reviews the recommendation.
   - If **Approved**, the decision is logged. (In Phase 1, the execution of the fix is done manually by the engineer. Future phases may integrate webhooks to CI/CD).
   - If **Rejected**, the manager must provide a `rationale`. The AI can optionally use this rationale in subsequent investigations.
4. **Audit Trail**: Every decision generates an immutable record in `recommendation_decisions` and `audit_logs`.

## Safety Constraints
- **NO Autonomous Execution**: The MVP explicitly prohibits SentinelAI from directly altering production infrastructure or databases. It only provides guidance.
