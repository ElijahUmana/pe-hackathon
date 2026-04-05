# Snip -- URL Shortener

![CI](https://github.com/elijahumana/pe-hackathon/actions/workflows/ci.yml/badge.svg)
![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-11%20containers-blue)
![Coverage](https://img.shields.io/badge/coverage-%E2%89%A570%25-brightgreen)

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
              | 2w x 2t | | 2w x 2t | | 2w x 2t |
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
     | (metrics scrape)   |    | (dashboards)|    |  (webhooks)  |
     +-------------------+    +------------+    +------+-------+
                                                       |
     +--------------+                          +-------v--------+
     | node-exporter|                          | webhook-receiver|
     | (host metrics)|                          | (logging +     |
     +--------------+                          |  Discord fwd)  |
                                               +----------------+
```

**11 containers.** 3 Flask app servers, 1 Nginx load balancer, 1 PostgreSQL database, 1 Redis cache, 1 Prometheus metrics collector, 1 Grafana dashboard, 1 Alertmanager, 1 Node Exporter (host metrics), 1 Webhook Receiver (alert logging with optional Discord forwarding).

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Web Framework | Flask 3.1 | HTTP routing, request handling |
| WSGI Server | Gunicorn 23 | Production server, 2 workers x 2 threads per instance |
| ORM | Peewee 3.17 | Database models, queries, migrations |
| Database | PostgreSQL 16 | Primary data store |
| Cache | Redis 7 | Redirect lookup cache (300s TTL) |
| Load Balancer | Nginx (alpine) | Least-connection routing across 3 instances |
| Metrics | Prometheus + prometheus_client | Scraping, time-series storage |
| Dashboards | Grafana | Real-time visualization |
| Alerting | Alertmanager + Webhook Receiver | Local logging with optional Discord forwarding |
| Load Testing | k6 | Bronze/Silver/Gold tier performance tests |
| Logging | python-json-logger | Structured JSON logs to stdout |
| Host Metrics | node-exporter | CPU, RAM, disk, network monitoring |
| Container Runtime | Docker + Docker Compose | Orchestration, health checks, restart policies |
| Package Manager | uv | Fast Python dependency management |
| CI/CD | GitHub Actions | Lint, test, coverage gate (70%), deploy gate |
| Language | Python 3.13 | |

## Key Features

- **Connection Pooling:** PooledPostgresqlDatabase with 20-connection pool eliminates per-request connect/disconnect overhead
- **Cache Warm-Up:** Top 100 active URLs pre-loaded into Redis on startup for instant cache hits
- **Composite Indexes:** `(short_code, is_active)` index optimizes the redirect hot path
- **Graceful Degradation:** Redis failure falls back to direct DB queries transparently
- **Soft Delete:** URLs are deactivated, not removed -- preserves history and analytics
- **Input Hardening:** Type validation, length limits (255 chars), URL format verification, FK existence checks
- **Bulk Import:** CSV upload endpoint with duplicate handling and row-level error recovery
- **Auto-Recovery:** Docker `restart: unless-stopped` policy auto-restarts crashed containers
- **Deploy Gating:** Deploy workflow depends on CI passing -- broken code cannot reach production

## Performance

Tested on a DigitalOcean s-1vcpu-1gb droplet (1 vCPU, 1 GB RAM + 2 GB swap, $6/mo) with 3 Flask instances behind Nginx (2 workers x 2 threads each = 12 handlers total).

| Tier | Concurrent Users | p95 Latency | Error Rate | Throughput | Status |
|------|-----------------|-------------|------------|------------|--------|
| Bronze | 50 | 707ms | 0.00% | 45.6 req/s | **PASS** |
| Silver | 200 | 2,020ms | 0.00% | 110 req/s | **PASS** |
| Gold | 500-600 | 6,420ms | 0.00% | 107 req/s | **PASS** |

**Key metrics:**
- Redirect latency (cache hit): **5-15ms** p50
- Cache hit ratio under load: **85%**
- Throughput: **107 req/s** sustained at 500+ concurrent users
- Auto-recovery from container crashes: **5-15 seconds**
- Cost: **$6/month** ($0.02/million requests)

See [docs/bottleneck-report.md](docs/bottleneck-report.md) for the full analysis.

## Monitoring

The system ships with a pre-built Grafana dashboard that visualizes all production metrics in real time.

**Dashboard panels:**
- Request Rate (by HTTP status code) -- see traffic volume and error spikes
- Error Rate (4xx and 5xx) -- percentage of failing requests
- Request Latency (p50, p95, p99) -- response time distribution
- Cache Hit Ratio -- Redis effectiveness (target: >80%)
- Active URLs, URLs Created rate, Redirects rate -- business metrics
- Instance Health -- UP/DOWN status per Flask instance

**Access:** `http://<host>:3000` (credentials: `admin` / `hackathon2026`)

**Alerting Pipeline:** Prometheus evaluates 10 alert rules and sends firing alerts to Alertmanager, which routes them to a custom webhook receiver. The webhook receiver:
- Logs all alerts to `/var/log/alerts.log` with full JSON payloads
- Saves individual evidence files per alert (timestamped JSON in `/app/evidence/`)
- Forwards to **Discord** with rich embeds when `DISCORD_WEBHOOK_URL` is set

**Discord Alert Features:**
- Severity-based colors (red = critical, orange = warning, green = resolved)
- Emoji indicators per severity level
- Clickable Grafana dashboard link in every alert
- Start/resolve timestamps for incident tracking
- Auto-resolution notifications when issues clear

**Alert Rules (10 total):**

| Alert | Condition | Severity |
|-------|-----------|----------|
| ServiceDown | Instance unreachable >15s | Critical |
| HighErrorRate | >10% 5xx errors for >2 min | Warning |
| HighLatency | p95 >2s for >3 min | Warning |
| HighMemoryUsage | >512MB for >5 min | Warning |
| HostHighCpuUsage | >80% CPU for >5 min | Warning |
| HostHighMemoryUsage | >85% memory for >5 min | Warning |
| HostDiskSpaceLow | <15% free for >5 min | Warning |
| HostDiskSpaceCritical | <5% free for >1 min | Critical |
| HostNetworkErrors | >10 errors/sec for >5 min | Warning |
| NodeExporterDown | Host metrics unavailable >30s | Critical |

**Quick Setup for Discord Alerts:**
```bash
# Set the Discord webhook URL on the Droplet
echo "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR/WEBHOOK" >> .env
docker compose up -d webhook-receiver
```

See [docs/runbook.md](docs/runbook.md) for alert response procedures and [docs/alert-pipeline.md](docs/alert-pipeline.md) for the complete pipeline architecture.

## Quick Start

### Local Development

```bash
# 1. Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync

# 2. Set up environment
cp .env.example .env

# 3. Start PostgreSQL and Redis
docker compose up db redis -d

# 4. Wait for database to be ready
docker compose exec db pg_isready -U postgres
# Should print: accepting connections

# 5. Seed the database
uv run python -m app.seed
# Should print: Loaded 400 users, 2000 URLs, 3422 events

# 6. Run the development server
uv run run.py
# Server at http://localhost:5000

# 7. Verify it works
curl http://localhost:5000/health
# Expected: {"database":"connected","status":"ok"}

# 8. Try a redirect
SHORT_CODE=$(curl -s http://localhost:5000/urls?per_page=1 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['short_code'])")
curl -v http://localhost:5000/$SHORT_CODE
# Expected: 302 redirect with Location header
```

### Full Stack (Docker Compose)

```bash
# 1. Start everything (11 containers, takes ~30s on first build)
docker compose up --build -d

# 2. Wait for all containers to be healthy
docker compose ps
# All should show "Up" status

# 3. Seed the database
docker compose exec app1 uv run python -m app.seed
# Should print: Loaded 400 users, 2000 URLs, 3422 events

# 4. Verify the application
curl http://localhost/health
# Expected: {"database":"connected","status":"ok"}

# 5. Verify load balancing (run multiple times, watch Nginx route to different instances)
for i in $(seq 1 5); do curl -s http://localhost/health; echo; done

# 6. Access services
# App:              http://localhost        (Nginx -> Flask x3)
# Grafana:          http://localhost:3000   (admin / hackathon2026)
# Prometheus:       http://localhost:9090
# Alertmanager:     http://localhost:9093
# Webhook Receiver: http://localhost:9094   (alert logging + Discord)
```

**Troubleshooting first start:**
- If `docker compose ps` shows a container restarting, check its logs: `docker compose logs <service>`
- If the database is not ready, wait 10 seconds and retry the seed command
- If port 80 is in use, see [docs/troubleshooting.md](docs/troubleshooting.md#port-conflicts)

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
| [docs/api.md](docs/api.md) | Full API reference with request/response examples for every endpoint |
| [docs/architecture.md](docs/architecture.md) | System design, data flow diagrams, schema, security, performance architecture |
| [docs/deployment.md](docs/deployment.md) | DigitalOcean deployment guide with zero-downtime strategy and smoke tests |
| [docs/environment-variables.md](docs/environment-variables.md) | Every environment variable documented with defaults and examples |
| [docs/runbook.md](docs/runbook.md) | Alert response procedures, recovery checklists, PromQL queries, post-incident template |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and fixes with diagnostic commands |
| [docs/decision-log.md](docs/decision-log.md) | Technical decision rationale for every major technology choice |
| [docs/capacity-plan.md](docs/capacity-plan.md) | Capacity planning, SLA definition, cost analysis, scaling projections |
| [docs/failure-modes.md](docs/failure-modes.md) | Failure mode analysis for every component with cascading scenarios |
| [docs/chaos-engineering.md](docs/chaos-engineering.md) | Chaos experiment playbook with methodology, tools, and continuous chaos strategy |
| [docs/bottleneck-report.md](docs/bottleneck-report.md) | Load test results, per-endpoint latency, cache analysis, resource utilization |
| [docs/alert-pipeline.md](docs/alert-pipeline.md) | Complete alerting pipeline: Prometheus rules, Alertmanager routing, webhook receiver |
| [docs/incident-diagnosis.md](docs/incident-diagnosis.md) | Real incident report from chaos engineering with full investigation walkthrough |

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
│   └── alertmanager.yml         # Alert routing (webhook receiver)
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
├── docker-compose.yml           # 11-service orchestration
├── Dockerfile                   # Python 3.13, Gunicorn, health check
├── pyproject.toml               # Dependencies, ruff, pytest config
└── run.py                       # Development entry point
```
