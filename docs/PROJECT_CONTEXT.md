# SentinelAI Project Context

## Project Vision
Build an industry-grade software platform that helps software engineers investigate production incidents. The platform will ingest application logs, metrics, traces, deployment information, and service information; detect abnormal behavior; correlate related events; use an AI investigation workflow to analyze evidence and identify probable root causes; and provide evidence-backed remediation recommendations with human approval.

## Problem Statement
Software engineers spend significant time investigating production incidents. The lack of correlated evidence and automated root cause analysis prolongs the Mean Time to Identify Root Cause (MTTI), leading to extended downtimes and business impact.

## Target Users
1. **Administrator**: Manage users, assign roles, register/configure services, view audit logs.
2. **Incident Manager**: Manage incidents, assign engineers, change severity/status, review investigations, review recommendations.
3. **Engineer**: View incidents, inspect telemetry, start investigations, review root-cause analysis, review remediation recommendations.
4. **Viewer**: Read-only access.

## MVP Scope
- **Authentication & RBAC**: Login, secure sessions, role-based authorization.
- **Service Management**: Register services, track owner, environment, version, repository, health.
- **Telemetry Ingestion**: Logs, metrics, traces with service associations and timestamps.
- **Incident Management**: Incident creation (auto/manual), severities (P1-P4), assignment, timeline, resolution.
- **Anomaly Detection**: Error-rate, latency, CPU, memory, and request-rate anomalies.
- **Event Correlation**: By time, service, trace, deployment, metric anomalies, log patterns.
- **AI Investigation**: Hypothesis generation, ranking, and evidence-backed root-cause explanation.
- **Recommendations**: Suggested remediation, risk/benefit analysis, and human approval.
- **Audit**: Logging of important system and user actions.

## Non-Goals
- Autonomous execution of destructive production actions (e.g., auto-rollbacks, db modifications).
- True multi-tenancy SaaS deployment initially (internal enterprise tool assumed).
- Real-time stream processing framework from scratch (using existing telemetry stores).

## Success Metrics
- **Business Metric**: Mean Time to Identify Root Cause (MTTI) vs. manual investigation.
- **Incident Detection**: Precision, Recall, F1, False-positive rate.
- **Root-Cause Analysis**: Top-1 accuracy, Top-3 accuracy.
- **AI Investigation**: Evidence accuracy, Unsupported-claim rate, Investigation completion rate.
- **System**: API latency, Telemetry ingestion rate, Investigation time.
