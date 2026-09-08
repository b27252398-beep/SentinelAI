import pytest
from fastapi.testclient import TestClient
from fastapi import APIRouter
from app.main import app
from app.core.exceptions import SentinelException

# Add temporary routes for testing exceptions
test_router = APIRouter()

@test_router.get("/test-sentinel-exception")
def trigger_sentinel_exception():
    raise SentinelException(message="Custom business logic error", status_code=422)

@test_router.get("/test-unhandled-exception")
def trigger_unhandled_exception():
    raise ValueError("Unexpected crash")

app.include_router(test_router)

client = TestClient(app, raise_server_exceptions=False)

def test_sentinel_exception_handler():
    response = client.get("/test-sentinel-exception")
    assert response.status_code == 422
    assert response.json() == {"error": "Custom business logic error"}

def test_global_exception_handler():
    response = client.get("/test-unhandled-exception")
    assert response.status_code == 500
    assert response.json() == {"error": "An internal server error occurred."}
