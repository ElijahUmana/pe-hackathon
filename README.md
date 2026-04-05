# Snip -- URL Shortener

A production-grade URL shortener built for the MLH Production Engineering Hackathon. The system handles URL creation, redirection with analytics tracking, and user management -- deployed behind a load-balanced, horizontally scaled architecture with full observability.

## Architecture

```
                         +-------------------+
                         |    Clients / k6   |
                         +--------+----------+
                                  |
                                  | :80
                                  v
                         +--------+----------+
                         |      Nginx        |
                         |  (Load Balancer)  |
                         |   least_conn      |
                         +--+-----+-------+--+
                            |     |       |
                   +--------+  +--+--+  +-+--------+
                   |           |     |             |
              +----v----+ +---v---+ +----v----+
              | Flask 1 | | Flask 2| | Flask 3 |
              | Gunicorn| | Gunicorn| | Gunicorn|
              | 4 workers| | 4 workers| | 4 workers|
              +----+----+ +---+---+ +----+----+
                   |           |           |
          +--------+-----------+-----------+--------+
          |                                         |
     +----v------+                          +-------v------+
     | PostgreSQL |                          |    Redis     |
     |  16-alpine |                          |  7-alpine    |
     |  (primary  |                          |  (cache,     |
     |   store)   |                          |   300s TTL)  |
     +------------+                          +--------------+

     +-------------------+    +------------+    +--------------+
     |    Prometheus      +--->|  Grafana   |    | Alertmanager |
     | (metrics scrape)   |    | (dashboards)|    |  (Discord)   |
     +-------------------+    +------------+    +--------------+
```

**9 containers.** 3 Flask app servers, 1 Nginx load balancer, 1 PostgreSQL database, 1 Redis cache, 1 Prometheus metrics collector, 1 Grafana dashboard, 1 Alertmanager.

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Web Framework | Flask 3.1 | HTTP routing, request handling |
| WSGI Server | Gunicorn 23 | Production server, 4 workers per instance |
| ORM | Peewee 3.17 | Database models, queries, migrations |
| Database | PostgreSQL 16 | Primary data store |
| Cache | Redis 7 | Redirect lookup cache (300s TTL) |
| Load Balancer | Nginx (alpine) | Least-connection routing across 3 instances |
| Metrics | Prometheus + prometheus_client | Scraping, time-series storage |
| Dashboards | Grafana | Real-time visualization |
| Alerting | Alertmanager | Discord notifications on incidents |
| Load Testing | k6 | Bronze/Silver/Gold tier performance tests |
| Logging | python-json-logger | Structured JSON logs to stdout |
| Container Runtime | Docker + Docker Compose | Orchestration, health checks, restart policies |
| Package Manager | uv | Fast Python dependency management |
| CI | GitHub Actions | Lint (ruff), test (pytest), coverage |
| Language | Python 3.13 | |

## Quick Start

### Local Development

```bash
# Install dependencies
uv sync

# Set up environment
cp .env.example .env

# Start PostgreSQL and Redis (if not running)
docker compose up db redis -d

# Create the database
createdb hackathon_db

# Seed the database
uv run python -m app.seed

# Run the development server
uv run run.py
# Server at http://localhost:5000

# Verify
curl http://localhost:5000/health
```

### Full Stack (Docker Compose)

```bash
# Start everything (9 containers)
docker compose up --build -d

# Seed the database
docker compose exec app1 uv run python -m app.seed

# Verify
curl http://localhost/health

# Access services
# App:          http://localhost        (Nginx -> Flask x3)
# Grafana:      http://localhost:3000   (admin / hackathon2026)
# Prometheus:   http://localhost:9090
# Alertmanager: http://localhost:9093
```

### Run Load Tests

```bash
# Bronze: 50 concurrent users
k6 run loadtests/k6/baseline.js

# Silver: 200 concurrent users
k6 run loadtests/k6/scaleout.js

# Gold: 500+ concurrent users
k6 run loadtests/k6/tsunami.js
```

### Run Tests

```bash
uv sync --all-extras
uv run pytest --cov=app --cov-report=term-missing
uv run ruff check .
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (DB connectivity) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/users` | List users (paginated) |
| `POST` | `/users` | Create user |
| `GET` | `/users/<id>` | Get user by ID |
| `PUT` | `/users/<id>` | Update user |
| `DELETE` | `/users/<id>` | Delete user |
| `GET` | `/urls` | List URLs (paginated) |
| `POST` | `/urls` | Create shortened URL |
| `GET` | `/urls/<id>` | Get URL by ID |
| `PUT` | `/urls/<id>` | Update URL |
| `DELETE` | `/urls/<id>` | Soft-delete URL |
| `GET` | `/urls/<id>/stats` | Redirect count for a URL |
| `GET` | `/urls/<id>/events` | Events for a URL |
| `GET` | `/events` | List all events (filterable) |
| `GET` | `/<short_code>` | Redirect to original URL (302) |

See [docs/api.md](docs/api.md) for full request/response documentation.

## Documentation

| Document | Description |
|---|---|
| [docs/api.md](docs/api.md) | Full API reference with examples |
| [docs/architecture.md](docs/architecture.md) | System design, data flow, schema |
| [docs/deployment.md](docs/deployment.md) | DigitalOcean deployment guide |
| [docs/environment-variables.md](docs/environment-variables.md) | Every env var documented |
| [docs/runbook.md](docs/runbook.md) | Alert response procedures |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and fixes |
| [docs/decision-log.md](docs/decision-log.md) | Technical decision rationale |
| [docs/capacity-plan.md](docs/capacity-plan.md) | Capacity planning and limits |
| [docs/failure-modes.md](docs/failure-modes.md) | Failure mode analysis |
| [docs/chaos-engineering.md](docs/chaos-engineering.md) | Chaos experiment playbook |

## Seed Data

The `seed_data/` directory contains CSV files provided by the hackathon platform:

- `users.csv` -- 400 users
- `urls.csv` -- 2,000 shortened URLs
- `events.csv` -- 3,422 events (created, redirect, updated, deleted)

Load them with:

```bash
# Local
uv run python -m app.seed

# Docker
docker compose exec app1 uv run python -m app.seed
```

## Project Structure

```
pe-hackathon/
├── app/
│   ├── __init__.py              # App factory, health check, error handlers
│   ├── cache.py                 # Redis client (singleton, graceful fallback)
│   ├── database.py              # Peewee DatabaseProxy, connection lifecycle
│   ├── logging_config.py        # Structured JSON logging setup
│   ├── metrics.py               # Prometheus counters, histograms, gauges
│   ├── seed.py                  # CSV seed data loader
│   ├── models/
│   │   ├── __init__.py          # Model exports
│   │   ├── user.py              # User model
│   │   ├── url.py               # URL model (short_code, soft delete)
│   │   └── event.py             # Event model (audit trail)
│   ├── routes/
│   │   ├── __init__.py          # Blueprint registration
│   │   ├── urls.py              # URL CRUD + redirect + stats
│   │   ├── users.py             # User CRUD
│   │   └── events.py            # Event listing + per-URL events
│   └── utils/
│       ├── short_code.py        # Cryptographic short code generation
│       └── validators.py        # URL and email validation
├── alertmanager/
│   └── alertmanager.yml         # Alert routing (Discord webhooks)
├── grafana/
│   ├── dashboards/
│   │   └── url-shortener.json   # Pre-built production dashboard
│   └── provisioning/
│       ├── dashboards/
│       │   └── dashboard.yml    # Dashboard auto-provisioning
│       └── datasources/
│           └── prometheus.yml   # Prometheus datasource config
├── loadtests/
│   └── k6/
│       ├── baseline.js          # Bronze: 50 VUs, p95 < 3s
│       ├── scaleout.js          # Silver: 200 VUs, p95 < 3s
│       └── tsunami.js           # Gold: 500+ VUs, p95 < 5s
├── nginx/
│   └── nginx.conf               # Load balancer config (least_conn)
├── prometheus/
│   ├── prometheus.yml           # Scrape config (3 Flask targets)
│   └── alert_rules.yml          # ServiceDown, HighErrorRate, HighLatency, HighMemoryUsage
├── seed_data/
│   ├── users.csv                # 400 users
│   ├── urls.csv                 # 2,000 URLs
│   └── events.csv               # 3,422 events
├── tests/
│   └── conftest.py              # Pytest fixtures (in-memory SQLite)
├── .env.example                 # Environment variable template
├── .github/workflows/ci.yml    # GitHub Actions CI pipeline
├── docker-compose.yml           # 9-service orchestration
├── Dockerfile                   # Python 3.13, Gunicorn, health check
├── pyproject.toml               # Dependencies, ruff, pytest config
└── run.py                       # Development entry point
```
