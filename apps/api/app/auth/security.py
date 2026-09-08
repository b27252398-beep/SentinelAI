import jwt
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Using Argon2id for password hashing as preferred
password_hash = PasswordHash((Argon2Hasher(),))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    try:
        decoded_token = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return decoded_token
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid token")
        return None
