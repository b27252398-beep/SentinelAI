import hashlib
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.telemetry.models import MachineCredential

security = HTTPBearer()

def generate_api_key():
    prefix = secrets.token_hex(8) # 16 chars
    secret = secrets.token_hex(32) # 64 chars
    return prefix, secret

def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()

def verify_machine_credential(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> MachineCredential:
    token = credentials.credentials
    if "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credential format"
        )
        
    prefix, secret = token.split(".", 1)
    
    cred = db.query(MachineCredential).filter(MachineCredential.key_prefix == prefix).first()
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credential"
        )
        
    if not secrets.compare_digest(cred.api_key_hash, hash_secret(secret)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credential"
        )
        
    if not cred.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential is revoked or inactive"
        )
        
    return cred
