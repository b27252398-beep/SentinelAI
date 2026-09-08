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
