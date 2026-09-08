import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "SentinelAI API"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    POSTGRES_DB: str = "sentinelai"
    POSTGRES_USER: str = "sentinel_user"
    POSTGRES_PASSWORD: str = "sentinel_dev_password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: str = "6379"

    # JWT Authentication
    JWT_SECRET_KEY: str = "unsafe-development-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @property
    def DATABASE_URL(self) -> str:
        # SQLAlchemy 2.x standard format: postgresql+psycopg://...
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
if settings.APP_ENV == "development":
    settings.CORS_ORIGINS.extend(["http://localhost:8000", "http://127.0.0.1:8000"])
