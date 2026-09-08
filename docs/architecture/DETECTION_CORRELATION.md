# Detection and Correlation Architecture

## Pipeline Flow
`Telemetry → Detection → Anomaly → Incident (if unhandled) → Event Correlation → Incident Timeline`

## Anomaly Detection
In the MVP, detection relies on deterministic statistical methods to avoid the overhead of training ML models on raw telemetry.
- **Threshold Detection**: Static hard limits (e.g., CPU > 90%).
- **Z-Score / Moving Average**: Detects sudden deviations in request rates or latencies relative to a rolling window (e.g., a 3-sigma deviation).
- Anomaly scoring determines the severity. High-severity anomalies trigger new **Incidents**.

## Event Correlation
When an Incident is created, the system must build context before the AI investigates.
- **Temporal Correlation**: Finds other anomalies or high-severity logs across *all* services that occurred within a defined window (e.g., $\pm 5$ minutes) of the primary anomaly.
- **Service Dependency Correlation**: (Future/Extension) Maps network topologies. For MVP, we rely strictly on temporal proximity and shared `trace_id`s.

## Distinction of Facts
- An anomaly record (e.g., "CPU at 95% at 10:05") is an **Observed Fact**.
- The correlation conclusion (e.g., "Service A latency spiked because Service B CPU spiked") is an **Inference**, which is deferred to the AI Investigation module rather than hardcoded into the correlation logic.
