# Docker and Deployment Architecture

The Phase 1 local development and MVP deployment rely on Docker Compose to orchestrate the monolith and its dependencies.

## Containers
1. **`frontend`**: Next.js Node container (Port 3000).
2. **`api`**: FastAPI Python container (Port 8000).
3. **`worker`**: Python container running Celery/Arq for background jobs (e.g., anomaly detection, AI queries, and scheduled 7-day raw telemetry cleanup).
4. **`db`**: PostgreSQL 16 container (Port 5432).
5. **`redis`**: Redis 7 container (Port 6379).
6. **`telemetry-simulator`**: Python script container generating mock traffic and incidents.

## Networking
- All backend services communicate on a private internal Docker bridge network.
- Only the `frontend` and `api` expose ports to the host machine for developer access.

## Environment & Secrets
- Configuration is injected via `.env` files (e.g., `TELEMETRY_RETENTION_DAYS=7`).
- Secrets (e.g., `LLM_API_KEY`, `POSTGRES_PASSWORD`) are never committed to version control.

## Volumes
- `postgres_data`: Persistent volume for database state.
- `redis_data`: Persistent volume for Redis queues (optional, for debugging).

## Startup Dependencies
- `api` depends on `db` and `redis` being healthy.
- `worker` depends on `api`, `db`, and `redis`.
- `frontend` depends on `api`.
