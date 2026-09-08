# Local Development Infrastructure

This document outlines the local infrastructure foundation for the SentinelAI platform.

## Prerequisites
- **Docker Desktop** or Docker Engine
- **Docker Compose**
- **Git**

## Infrastructure Components
- **PostgreSQL 16**: Primary relational datastore (`sentinelai_postgres`).
- **Redis 7**: Message broker and caching layer (`sentinelai_redis`).

## Environment Variables
The application uses environment variables for configuration. Copy `.env.example` to `.env` to start locally.
Never commit real secrets to the repository.

### Default Database Connections
- **PostgreSQL**: `postgresql://sentinel_user:sentinel_dev_password@localhost:5432/sentinelai`
- **Redis**: `redis://localhost:6379`

## Starting Infrastructure
To validate the configuration:
```bash
docker compose config
```
To start the services in the background:
```bash
docker compose up -d
```

## Checking Service Status
To check if the containers are running and healthy:
```bash
docker compose ps
```

## Viewing Logs
To view logs for a specific service:
```bash
docker compose logs -f postgres
docker compose logs -f redis
```

## Stopping Infrastructure
To stop the services without removing data:
```bash
docker compose stop
```
To stop and remove the containers:
```bash
docker compose down
```

## Resetting Development Containers/Volumes
**⚠️ CLEAR WARNING: The following command will irreversibly delete all local PostgreSQL data and reset the infrastructure to a pristine state.**
```bash
docker compose down -v
```

## Troubleshooting
- **Port Conflicts**: If port `5432` or `6379` is already in use by a local installation, you must stop the local service or change the exposed ports in `docker-compose.yml`.
- **Unhealthy Containers**: Use `docker compose logs <service>` to determine why a service is failing to start or pass its healthcheck.

## Backend (FastAPI) Setup

The backend API is located in `apps/api/` and requires Python 3.13+.

### 1. PostgreSQL/Redis Prerequisites
Ensure the Docker Compose infrastructure is running (see *Starting Infrastructure* above) before running the API locally, as it relies on PostgreSQL and Redis.

### 2. Environment Configuration
From the repository root, copy `.env.example` to `.env`. The backend automatically loads variables from this file.

### 3. Virtual Environment & Dependencies
Navigate to the `apps/api/` directory:
```bash
cd apps/api
python -m venv .venv
# Activate environment (Windows)
.venv\Scripts\activate
# Activate environment (Unix)
source .venv/bin/activate

# Install dependencies (including development tools)
pip install -e ".[dev]"
```

### 4. Running the API
Start the FastAPI server with Uvicorn:
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.
- API Docs: `http://127.0.0.1:8000/api/docs`

### 5. Health & Readiness Endpoints
- **GET `/health`**: Returns basic status `{"status": "ok"}` indicating the application is running.
- **GET `/ready`**: Connects to PostgreSQL and Redis. Returns `200 OK` if both are accessible, or `503 Service Unavailable` if either dependency is offline.

### 6. Running Tests
To execute the backend test suite:
```bash
pytest -v
```
