import pytest
from datetime import datetime, timezone
import uuid
from app.investigations.models import InvestigationEvidence
from app.investigations.normalizer import _truncate_stack_trace, _get_priority, normalize_evidence

def test_truncate_stack_trace():
    short_trace = "line1\nline2\nline3"
    assert _truncate_stack_trace(short_trace) == short_trace
    
    long_trace = "1\n2\n3\n4\n5\n6\n7\n8\n9"
    trunc = _truncate_stack_trace(long_trace)
    assert "1\n2\n3" in trunc
    assert "[middle frames omitted]" in trunc
    assert "7\n8\n9" in trunc

def test_priority():
    ev_anomaly = InvestigationEvidence(source_type="anomaly", timestamp=datetime.now(timezone.utc), source_identifier="1", deep_copied_payload={})
    assert _get_priority(ev_anomaly) == 1
    
    ev_err_log = InvestigationEvidence(source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="2", deep_copied_payload={"severity": "ERROR"})
    assert _get_priority(ev_err_log) == 2
    
    ev_warn_log = InvestigationEvidence(source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="3", deep_copied_payload={"severity": "WARN"})
    assert _get_priority(ev_warn_log) == 4
    
    ev_trace_err = InvestigationEvidence(source_type="trace", timestamp=datetime.now(timezone.utc), source_identifier="4", deep_copied_payload={"status": {"code": "Error"}})
    assert _get_priority(ev_trace_err) == 2
    
    ev_trace_ok = InvestigationEvidence(source_type="trace", timestamp=datetime.now(timezone.utc), source_identifier="5", deep_copied_payload={"status": {"code": "Ok"}})
    assert _get_priority(ev_trace_ok) == 3

def test_normalize_evidence_budget_enforcement():
    # create 3000 evidences to see if budget limits it. 
    # Max size is ~200KB. We'll add some huge payload to force truncate.
    large_payload = {"body": "A" * 100000} # 100KB each
    
    evs = [
        InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="1", deep_copied_payload=large_payload),
        InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="2", deep_copied_payload=large_payload),
        InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="3", deep_copied_payload=large_payload)
    ]
    
    res = normalize_evidence(evs)
    # The budget is 200KB. 3 * 100KB = 300KB > 200KB.
    # It should truncate the last one.
    assert "WARNING: Token budget exceeded" in res
    
    # Check that high priority is kept over low priority
    ev_high = InvestigationEvidence(id=uuid.uuid4(), source_type="anomaly", timestamp=datetime.now(timezone.utc), source_identifier="4", deep_copied_payload={"feature": "CPU_HIGH"})
    ev_low = InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="5", deep_copied_payload=large_payload)
    ev_low2 = InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="6", deep_copied_payload=large_payload)
    ev_low3 = InvestigationEvidence(id=uuid.uuid4(), source_type="log", timestamp=datetime.now(timezone.utc), source_identifier="7", deep_copied_payload=large_payload)
    
    res2 = normalize_evidence([ev_low, ev_high, ev_low2, ev_low3])
    assert "CPU_HIGH" in res2 # high priority preserved
    assert "WARNING: Token budget exceeded" in res2
