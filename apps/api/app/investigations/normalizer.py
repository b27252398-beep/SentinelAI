import json
from typing import List, Dict, Any, Tuple
from app.investigations.models import InvestigationEvidence

# Token budget constants
MAX_NORMALIZED_SIZE_BYTES = 200 * 1024  # ~200KB for 64k tokens limit

def _truncate_stack_trace(stack_trace: str) -> str:
    if not stack_trace:
        return stack_trace
    
    lines = stack_trace.strip().split('\n')
    if len(lines) <= 6:
        return stack_trace
    
    top_3 = lines[:3]
    bottom_3 = lines[-3:]
    return "\n".join(top_3 + ["... [middle frames omitted] ..."] + bottom_3)

def _get_priority(ev: InvestigationEvidence) -> int:
    """
    1. Anomalies
    2. Spans/Logs with Errors
    3. Upstream/Downstream Traces related to Errors (simplified: spans that aren't errors)
    4. Warnings
    5. Info/Debug Logs & Normal Metrics
    """
    if ev.source_type == "anomaly":
        return 1
    
    payload = ev.deep_copied_payload or {}
    
    # Check for errors in logs/traces
    if ev.source_type == "log":
        sev = str(payload.get("severity", "")).upper()
        if sev in ("ERROR", "FATAL", "CRITICAL") or payload.get("severity_number", 0) >= 17:
            return 2
        elif sev == "WARN" or payload.get("severity_number", 0) >= 13:
            return 4
        return 5
        
    if ev.source_type == "trace":
        # Look for HTTP 5xx or span error status
        attrs = payload.get("event_attributes", {})
        status = attrs.get("http.status_code") or attrs.get("http.response.status_code")
        if status and int(status) >= 500:
            return 2
        if payload.get("status", {}).get("code") == "Error":
            return 2
        return 3 # Non-error trace (e.g. part of an error distributed trace)
        
    if ev.source_type == "metric":
        return 5
        
    return 5

def normalize_evidence(evidence_list: List[InvestigationEvidence]) -> str:
    """
    Condenses the raw JSON into a token-efficient text format.
    Prioritizes critical fields, truncates stack traces, and drops
    records if the total size exceeds the budget.
    """
    # Sort evidence by priority (1 is highest), then by chronological timestamp (newest first for dropping? 
    # Actually design says: "drop oldest records first" if within same priority.)
    # We sort by priority ASC, timestamp DESC. Then we can drop from the end of the list.
    
    sorted_ev = sorted(evidence_list, key=lambda x: (_get_priority(x), -x.timestamp.timestamp()))
    
    normalized_blocks = []
    current_size = 0
    
    # We process in priority order. If we hit the limit, we stop.
    for ev in sorted_ev:
        block_lines = []
        block_lines.append(f"ID: {ev.id}")
        block_lines.append(f"Type: {ev.source_type}")
        block_lines.append(f"Timestamp: {ev.timestamp.isoformat()}")
        if ev.service_id:
            block_lines.append(f"Service: {ev.service_id}")
            
        payload = ev.deep_copied_payload or {}
        
        if ev.source_type == "anomaly":
            block_lines.append(f"Feature: {payload.get('feature')}")
            block_lines.append(f"Severity: {payload.get('severity')}")
            block_lines.append(f"Status: {payload.get('status')}")
            
        elif ev.source_type == "log":
            block_lines.append(f"Message: {payload.get('body', '')}")
            exc = payload.get("event_attributes", {}).get("exception.type")
            if exc:
                block_lines.append(f"Exception: {exc}")
                msg = payload.get("event_attributes", {}).get("exception.message")
                if msg:
                    block_lines.append(f"Error Msg: {msg}")
                st = payload.get("event_attributes", {}).get("exception.stacktrace")
                if st:
                    block_lines.append(f"Stacktrace: {_truncate_stack_trace(st)}")
                    
        elif ev.source_type == "trace":
            block_lines.append(f"Trace ID: {payload.get('trace_id')}")
            block_lines.append(f"Span ID: {payload.get('span_id')}")
            parent = payload.get('parent_span_id')
            if parent:
                block_lines.append(f"Parent Span ID: {parent}")
            block_lines.append(f"Name: {payload.get('name')}")
            
            attrs = payload.get("event_attributes", {})
            status = attrs.get("http.status_code") or attrs.get("http.response.status_code")
            if status:
                block_lines.append(f"HTTP Status: {status}")
                
            # If there's an exception recorded as an event in the span
            for event in payload.get("events", []):
                if event.get("name") == "exception":
                    e_attrs = event.get("attributes", {})
                    if "exception.type" in e_attrs:
                        block_lines.append(f"Exception: {e_attrs['exception.type']}")
                    if "exception.stacktrace" in e_attrs:
                        block_lines.append(f"Stacktrace: {_truncate_stack_trace(e_attrs['exception.stacktrace'])}")
                        
        elif ev.source_type == "metric":
            block_lines.append(f"Metric: {payload.get('name')}")
            block_lines.append(f"Value: {payload.get('value')} {payload.get('unit', '')}")
            
        block_str = "\n".join(block_lines) + "\n---\n"
        block_size = len(block_str.encode("utf-8"))
        
        if current_size + block_size > MAX_NORMALIZED_SIZE_BYTES:
            normalized_blocks.append("WARNING: Token budget exceeded. Lowest priority and oldest evidence truncated.")
            break
            
        normalized_blocks.append(block_str)
        current_size += block_size
        
    return "===EVIDENCE_START===\n" + "".join(normalized_blocks) + "===EVIDENCE_END==="
