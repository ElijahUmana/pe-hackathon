# Environment Variables

## Application Variables

These are consumed by the Flask application (`app/__init__.py`, `app/database.py`, `app/cache.py`, `app/logging_config.py`).

| Variable | Description | Default | Required | Example |
|---|---|---|---|---|
| `DATABASE_NAME` | PostgreSQL database name | `hackathon_db` | No | `hackathon_db` |
| `DATABASE_HOST` | PostgreSQL host address | `localhost` | No | `db` (Docker), `localhost` (local) |
| `DATABASE_PORT` | PostgreSQL port | `5432` | No | `5432` |
| `DATABASE_USER` | PostgreSQL username | `postgres` | No | `postgres` |
| `DATABASE_PASSWORD` | PostgreSQL password | `postgres` | No | `postgres` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` | No | `redis://redis:6379/0` |
| `LOG_LEVEL` | Logging verbosity | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `FLASK_DEBUG` | Flask debug mode | (not set) | No | `true` (local dev only) |
| `INSTANCE_ID` | Identifies this app instance in logs | (not set) | No | `app1`, `app2`, `app3` |

### Notes

- In Docker Compose, all variables are set in the `environment` block of each service in `docker-compose.yml`. The `.env` file is only used for local development.
- `REDIS_URL` follows the standard Redis URL format: `redis://[:password@]host[:port][/db-number]`
- `LOG_LEVEL` accepts standard Python logging levels. It controls both the root logger and the stream handler.
- `FLASK_DEBUG` should never be set to `true` in production. It is not set in the Docker Compose configuration.
- `INSTANCE_ID` is informational. It is passed as an environment variable but not currently read by the application code. It is available for log correlation if needed.

## PostgreSQL Variables

These are set on the `db` service in `docker-compose.yml` and consumed by the PostgreSQL container.

| Variable | Description | Default | Required | Example |
|---|---|---|---|---|
| `POSTGRES_DB` | Database to create on first run | (none) | Yes | `hackathon_db` |
| `POSTGRES_USER` | Superuser username | `postgres` | No | `postgres` |
| `POSTGRES_PASSWORD` | Superuser password | (none) | Yes | `postgres` |

## Grafana Variables

These are set on the `grafana` service in `docker-compose.yml`.

| Variable | Description | Default | Required | Example |
|---|---|---|---|---|
| `GF_SECURITY_ADMIN_USER` | Admin username | `admin` | No | `admin` |
| `GF_SECURITY_ADMIN_PASSWORD` | Admin password | `admin` | No | `hackathon2026` |
| `GF_USERS_ALLOW_SIGN_UP` | Allow self-registration | `true` | No | `false` |

## CI Variables

These are set in `.github/workflows/ci.yml` for the test job.

| Variable | Description | Value |
|---|---|---|
| `DATABASE_NAME` | Test database name | `test_db` |
| `DATABASE_HOST` | Postgres service in CI | `localhost` |
| `DATABASE_PORT` | Postgres port in CI | `5432` |
| `DATABASE_USER` | Postgres user in CI | `postgres` |
| `DATABASE_PASSWORD` | Postgres password in CI | `postgres` |

## Configuration Files vs Environment Variables

| Setting | Configured Via | Location |
|---|---|---|
| Nginx upstream servers | Config file | `nginx/nginx.conf` |
| Prometheus scrape targets | Config file | `prometheus/prometheus.yml` |
| Alert rules | Config file | `prometheus/alert_rules.yml` |
| Alertmanager routing | Config file | `alertmanager/alertmanager.yml` |
| Grafana datasource | Config file | `grafana/provisioning/datasources/prometheus.yml` |
| Grafana dashboard | Config file | `grafana/dashboards/url-shortener.json` |
| Gunicorn workers | Dockerfile CMD | `Dockerfile` |
| Redis cache TTL | Application code | `app/routes/urls.py` (hardcoded 300s) |
| Short code length | Application code | `app/utils/short_code.py` (hardcoded 6) |
| Pagination defaults | Application code | Route handlers (hardcoded 25/100) |

## Local Development (.env file)

Copy `.env.example` to `.env` for local development:

```bash
cp .env.example .env
```

Contents of `.env.example`:
```
FLASK_DEBUG=true
DATABASE_NAME=hackathon_db
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

The `.env` file is loaded by `python-dotenv` in `create_app()`. It is gitignored and should never be committed.
