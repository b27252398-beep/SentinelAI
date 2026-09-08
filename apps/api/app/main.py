from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.api import health
from app.auth import router as auth_router
from app.services import router as services_router
from app.telemetry import router as telemetry_router
from app.detection import router as detection_router

# Configure structured logging
setup_logging()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from starlette.responses import JSONResponse

class MaxPayloadSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/telemetry/ingest") and request.method == "POST":
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > 5 * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "Payload Too Large (Exceeds 5 MiB)"})
            # To handle missing content-length, we rely on the ASGI server (like uvicorn)
            # or streaming constraints, but MVP enforces the header explicitly.
        return await call_next(request)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MaxPayloadSizeMiddleware)

# Exception handlers
setup_exception_handlers(app)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth_router.router)
app.include_router(services_router.router, prefix="/api/v1")
app.include_router(telemetry_router.router, prefix="/api/v1/telemetry", tags=["Telemetry"])
app.include_router(detection_router.router, prefix="/api/v1/detection", tags=["Detection"])
