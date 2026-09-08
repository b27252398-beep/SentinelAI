import logging
from typing import Optional, Dict, Any
from uuid import UUID

logger = logging.getLogger("sentinelai.audit")

def log_event(
    action: str, 
    actor_id: Optional[UUID], 
    resource_id: Optional[UUID], 
    context: Optional[Dict[str, Any]] = None
):
    """
    Audit logging contract for SentinelAI.
    Currently logs to stdout. A future implementation could write to 
    an audit_logs table or a SIEM.
    """
    actor = str(actor_id) if actor_id else "System"
    res = str(resource_id) if resource_id else "None"
    ctx_str = str(context) if context else "{}"
    
    logger.info(f"AUDIT_EVENT | action={action} | actor_id={actor} | resource_id={res} | context={ctx_str}")
