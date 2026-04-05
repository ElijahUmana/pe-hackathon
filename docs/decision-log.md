# Technical Decision Log

This document records the rationale behind major technology and design choices.

---

## DEC-001: Flask as the Web Framework

**Decision:** Use Flask as the HTTP framework.

**Context:** The MLH PE Hackathon provided a starter template built on Flask + Peewee + PostgreSQL. The template included the app factory pattern, database proxy setup, and project structure.

**Rationale:**
- The hackathon template was Flask-based, and switching frameworks would mean rebuilding all scaffolding from scratch with no benefit.
- Flask is lightweight and minimal -- it provides routing, request/response handling, and blueprints without imposing opinions on database access, serialization, or project layout.
- The blueprint system maps naturally to the three resource types (users, urls, events), keeping route files small and focused.
- Flask's ecosystem provides everything needed: `flask.jsonify` for JSON responses, `flask.redirect` for the core redirect operation, `flask.Blueprint` for modular routing.

**Tradeoffs:**
- No built-in async support (not needed for this workload since Gunicorn handles concurrency at the process level).
- No built-in request validation (handled manually with explicit checks in route handlers).

---

## DEC-002: Peewee ORM

**Decision:** Use Peewee as the ORM layer.

**Context:** The hackathon template used Peewee with a `DatabaseProxy` pattern for deferred database initialization.

**Rationale:**
- Required by the template. Peewee is lightweight (single file), which fits the hackathon's constraints.
- The `DatabaseProxy` pattern allows the app factory to configure the database at runtime, supporting both PostgreSQL (production) and SQLite (testing).
- `playhouse.shortcuts.model_to_dict` provides zero-config serialization of model instances to dictionaries, which pair directly with `flask.jsonify`.
- Peewee's query builder is expressive enough for our needs: filtering, pagination, aggregation, and foreign key traversal.

**Tradeoffs:**
- Peewee is not async-capable, but this is irrelevant since we use synchronous Gunicorn workers.
- Migration tooling is less mature than Alembic (SQLAlchemy). For this project, we use `create_tables(safe=True)` and the seed script for schema management.

---

## DEC-003: PostgreSQL

**Decision:** Use PostgreSQL 16 as the primary data store.

**Context:** The hackathon template specified PostgreSQL. The seed data was provided as CSV files designed for PostgreSQL.

**Rationale:**
- Required by the template.
- PostgreSQL handles concurrent writes well (MVCC), which matters with 3 app instances writing events simultaneously.
- UNIQUE constraints on `username`, `email`, and `short_code` are enforced at the database level, preventing duplicates regardless of which app instance handles the request.
- The `pg_isready` health check integrates with Docker Compose's `healthcheck` directive, ensuring app containers only start after the database is accepting connections.

**Tradeoffs:**
- Heavier than SQLite for development. Mitigated by using SQLite in-memory for unit tests via the `DatabaseProxy` pattern.

---

## DEC-004: Redis for Caching

**Decision:** Use Redis as a read-through cache for URL redirect lookups.

**Context:** The hackathon performance tiers require sub-3-second p95 latency under load. Without caching, every redirect requires a PostgreSQL query plus an event INSERT, adding significant latency under high concurrency.

**Rationale:**
- Redirect is the highest-traffic operation (70-80% of load test traffic). Caching the URL lookup eliminates the SELECT query on repeated accesses.
- Redis operates in-memory with sub-millisecond response times, making it ideal for this hot path.
- A 600-second TTL balances freshness (URL updates/deletions are reflected within 10 minutes) against cache efficiency. The longer TTL, combined with full warm-up of all active URLs on startup, achieves 95%+ hit ratio.
- Explicit cache invalidation on UPDATE and DELETE operations ensures immediate consistency for administrative actions.
- Graceful degradation: if Redis is unavailable, the application falls back to PostgreSQL with no code changes. All Redis calls are wrapped in try/except blocks.

**Cache key design:** `url:{short_code}` -- simple, predictable, easy to debug with `redis-cli`.

**Tradeoffs:**
- Redirect events are still written to PostgreSQL on every access (even cache hits), so the database is still in the write path.
- Stale reads are possible within the TTL window if a URL is updated through a mechanism that bypasses cache invalidation (there is no such mechanism currently, but the risk exists).

---

## DEC-005: Nginx for Load Balancing

**Decision:** Use Nginx as a reverse proxy and load balancer in front of 3 Flask instances.

**Context:** The hackathon requires demonstrating horizontal scaling. A single Flask+Gunicorn instance can be vertically scaled (more workers), but horizontal scaling requires a load balancer.

**Rationale:**
- Nginx is the industry standard for reverse proxying Python WSGI applications.
- The `least_conn` algorithm distributes requests to the server with the fewest active connections, naturally handling variance in request processing time (cache hits are faster than misses).
- Nginx handles HTTP parsing and connection management, offloading this from Gunicorn.
- Structured JSON access logs from Nginx provide request-level observability at the edge.
- The `/nginx-health` and `/nginx-status` endpoints provide load balancer health and connection metrics without hitting the upstream Flask servers.

**Tradeoffs:**
- Adds another container and configuration file to maintain.
- No automatic failover configuration (Nginx will retry on upstream errors by default, but does not remove dead backends from the pool). For this project, Docker's restart policy handles backend recovery.

---

## DEC-006: Docker Compose for Orchestration

**Decision:** Use Docker Compose to orchestrate all 11 services.

**Context:** The hackathon requires deploying to a single DigitalOcean droplet. The system includes 11 components that need to start in a specific order with health check dependencies.

**Rationale:**
- Docker Compose handles service dependency ordering via `depends_on` with `condition: service_healthy`, ensuring Flask instances don't start until PostgreSQL and Redis are ready.
- The `restart: unless-stopped` policy provides automatic recovery for chaos engineering scenarios (killing containers to demonstrate resilience).
- Named volumes (`postgres_data`, `prometheus_data`, `grafana_data`) persist data across container restarts and redeployments.
- All 11 services are defined in a single `docker-compose.yml` file, making the entire system reproducible with a single `docker compose up`.

**Tradeoffs:**
- Docker Compose runs on a single host, so there is no cross-node redundancy. The database is a single point of failure.
- No rolling deployments -- `docker compose up --build -d` rebuilds and restarts all changed services simultaneously.

---

## DEC-007: Gunicorn as the WSGI Server

**Decision:** Use Gunicorn with gthread workers (2 workers x 2 threads) per instance as the production WSGI server.

**Context:** Flask's built-in development server (`flask run`) is single-threaded and not suitable for production traffic.

**Rationale:**
- Gunicorn pre-forks worker processes, allowing each Flask instance to handle multiple concurrent requests.
- 2 workers x 2 threads per instance, across 3 instances, provides 12 concurrent request handlers.
- `gthread` workers use threads within each worker process, reducing memory overhead compared to pure sync workers while improving throughput for I/O-bound operations (database queries, Redis lookups).
- The `--timeout 120` setting prevents worker starvation under sustained load.
- `--access-logfile -` logs requests to stdout, which Docker captures and makes available via `docker compose logs`.

**Tradeoffs:**
- Threaded workers share GIL within each process, so CPU-bound work within a single worker is serialized. This is acceptable because the workload is I/O-bound (database queries, Redis lookups).
- Memory usage scales with worker count (each worker loads a full copy of the Flask application), but threads within a worker share memory, making gthread more memory-efficient than pure sync workers at the same concurrency level.

---

## DEC-008: Prometheus + Grafana for Monitoring

**Decision:** Use Prometheus for metrics collection and Grafana for visualization, with Alertmanager for alert routing.

**Context:** The hackathon requires monitoring and observability. The stack needed to support custom application metrics (not just infrastructure metrics).

**Rationale:**
- Prometheus is the industry standard for application metrics in containerized environments.
- The `prometheus_client` Python library integrates natively, providing Counters, Histograms, and Gauges with minimal code.
- Pull-based scraping (Prometheus scrapes `/metrics` every 10 seconds) requires no push infrastructure or additional dependencies in the application.
- Grafana provides pre-built visualization for Prometheus data with a provisioning system that allows dashboards to be version-controlled as JSON files.
- Alertmanager routes alerts based on severity to a webhook receiver that logs alerts locally and optionally forwards them to Discord.
- 7-day data retention in Prometheus is sufficient for the hackathon evaluation period.

**Tradeoffs:**
- Five additional containers (Prometheus, Grafana, Alertmanager, Node Exporter, Webhook Receiver) consume memory on the resource-constrained droplet.
- The Grafana dashboard JSON file is verbose (1000+ lines) but is auto-provisioned, requiring no manual setup.

---

## DEC-009: k6 for Load Testing

**Decision:** Use k6 for load testing with three tier-specific scripts.

**Context:** The hackathon defines three performance tiers: Bronze (50 concurrent users), Silver (200 concurrent users), Gold (500+ concurrent users).

**Rationale:**
- k6 was recommended by the hackathon as the load testing tool.
- k6 scripts are written in JavaScript, making them readable and easy to modify.
- The staged ramp-up/ramp-down pattern simulates realistic traffic growth.
- Built-in threshold checks (`http_req_duration`, custom `errors` rate) provide pass/fail criteria aligned with hackathon requirements.
- Custom metrics (`redirect_latency`, `create_latency`) allow per-operation analysis.
- The traffic mix in each script reflects realistic URL shortener usage (70-80% redirects, 10-15% reads, 5-10% creates).

**Test scripts:**
- `baseline.js` (Bronze): 50 VUs, p95 < 3s, 3-minute hold
- `scaleout.js` (Silver): 200 VUs, p95 < 3s, 3-minute hold
- `tsunami.js` (Gold): 500 VUs ramping to 600, p95 < 5s, 3-minute hold

---

## DEC-010: Structured JSON Logging

**Decision:** Use `python-json-logger` for structured JSON log output.

**Context:** The hackathon requires machine-parseable logs. Traditional text logs are difficult to filter and aggregate.

**Rationale:**
- JSON logs can be parsed by any log aggregation tool (ELK, Loki, CloudWatch).
- Each log entry includes a timestamp, level, logger name, and message as structured fields.
- Request logging middleware adds method, path, status code, remote address, and user agent to every request log.
- Nginx is also configured with a JSON log format (`json_combined`), ensuring all layers produce parseable output.
- The `werkzeug` logger is suppressed to WARNING level to reduce noise from Flask's default request logging.

**Tradeoffs:**
- JSON logs are harder to read directly with `docker compose logs`. Use `jq` for filtering:
  ```bash
  docker compose logs app1 | jq '.message'
  ```

---

## DEC-011: Soft Deletes for URLs

**Decision:** DELETE requests on URLs set `is_active = false` rather than removing the row.

**Context:** The hackathon seed data includes event history tied to URL records. Hard-deleting a URL would violate the foreign key constraint on the events table, or require cascading deletes that destroy audit history.

**Rationale:**
- Soft deletes preserve the complete audit trail. Every event (created, redirect, updated, deleted) remains queryable.
- The redirect handler filters on `is_active = True`, so soft-deleted URLs correctly return 404.
- The `is_active` flag can be toggled via PUT, allowing URLs to be reactivated.
- A `deleted` event is recorded, maintaining the event log's completeness.

**Tradeoffs:**
- Soft-deleted URLs still consume database storage and appear in `GET /urls` listings (they show `is_active: false`).
- Cache invalidation is required on soft delete to prevent stale redirects.

---

## DEC-012: Cryptographic Short Code Generation

**Decision:** Use `secrets.choice` for short code generation instead of `random.choice` or hash-based approaches.

**Context:** Short codes must be unique and unpredictable. The hackathon "Twin's Paradox" hint specifies that identical URLs must produce different short codes.

**Rationale:**
- `secrets.choice` uses the OS cryptographic random number generator, making codes unpredictable.
- Random generation (vs. sequential or hash-based) ensures two identical URLs always get different codes.
- 6 characters from a 62-character alphabet (a-z, A-Z, 0-9) provides 62^6 = 56.8 billion possible codes, making collisions negligible.
- A retry loop (up to 10 attempts) handles the rare collision case by generating a new code.

**Tradeoffs:**
- No way to derive the original URL from the short code (by design).
- Slightly more database writes on collision (statistically negligible).

---

## DEC-013: Webhook Receiver with Optional Discord Forwarding

**Decision:** Use a custom webhook receiver as the Alertmanager notification target instead of sending directly to Discord.

**Context:** Alertmanager supports sending alerts directly to external webhook URLs (such as Discord). However, relying solely on an external service for alert logging means alert history is lost if the external service is unavailable, and there is no local evidence trail for incident investigation.

**Rationale:**
- The webhook receiver logs all alerts locally to `/var/log/alerts.log` (append-only structured JSON) and writes individual evidence files to `/app/evidence/`. This provides a persistent, self-contained audit trail regardless of external service availability.
- Discord forwarding is optional, configured via the `DISCORD_WEBHOOK_URL` environment variable. When not set, the receiver still logs everything locally.
- Individual evidence JSON files (named `alert_{name}_{status}_{timestamp}.json`) make it straightforward to investigate specific incidents and provide hackathon evidence.
- The receiver is a minimal Python HTTP server with zero external dependencies (stdlib only), keeping the container image small and fast to start.
- The evidence directory is mounted as a Docker volume, persisting files across container restarts.

**Tradeoffs:**
- Adds one more container to the stack (11 total instead of 10).
- Requires maintaining a small custom application (though it is ~100 lines of stdlib Python with no dependencies).
- Alert delivery to Discord is now two hops (Alertmanager -> Webhook Receiver -> Discord) instead of one, adding marginal latency to external notifications.

---

## DEC-014: Node Exporter for Host Metrics

**Decision:** Deploy Node Exporter to collect host-level system metrics (CPU, RAM, disk, network).

**Context:** Application-level metrics from Flask (`http_requests_total`, `http_request_duration_seconds`, etc.) show how the application is performing, but do not reveal whether the underlying host is the bottleneck. During load testing, we needed to correlate application latency with host CPU saturation.

**Rationale:**
- Node Exporter exposes standard system metrics in Prometheus format, allowing infrastructure alert rules (HostHighCpuUsage, HostHighMemoryUsage, HostDiskSpaceLow, HostNetworkErrors) to fire based on actual host conditions.
- Running with `pid: host` and read-only mounts for `/proc`, `/sys`, and `/` provides accurate host-level metrics from inside a container.
- CPU saturation was identified as the primary bottleneck during load testing. Node Exporter's `node_cpu_seconds_total` metric enabled the HostHighCpuUsage alert that fired at 96.68% during chaos experiments.

**Tradeoffs:**
- Adds one more container and requires `pid: host` and read-only host filesystem mounts, which slightly increases the attack surface.
- Minimal resource overhead (~10-15 MB memory).

---

## DEC-015: PostgreSQL synchronous_commit=off

**Decision:** Disable synchronous WAL commit in PostgreSQL (`synchronous_commit=off`).

**Context:** Every URL redirect writes an event to the database (Oracle Hint 2: "Unseen Observer"). At 600 concurrent users generating ~180 event INSERTs per second, the WAL flush on each commit was the dominant bottleneck. Each INSERT waited ~5ms for the WAL to be flushed to disk, directly adding to redirect latency.

**Rationale:**
- `synchronous_commit=off` allows PostgreSQL to acknowledge the INSERT before the WAL is flushed, reducing event write latency from ~5ms to ~0.5ms.
- At 217 req/s with ~80% being redirects, this eliminates ~4.5ms per redirect -- the single largest optimization.
- Data consistency is NOT compromised: the transaction is still written to the WAL, just asynchronously. In the worst case (server crash), up to ~100ms of recent commits could be lost.
- For a URL shortener's redirect analytics, losing a few events in a catastrophic crash is an acceptable tradeoff for a 37% p95 latency reduction.
- Result: Silver p95 improved from 1,630ms to 1,040ms. Gold p95 improved from 4,680ms to 2,970ms.

**Tradeoffs:**
- In a catastrophic PostgreSQL crash (not a Docker restart, but an actual OS-level crash), the last ~100ms of committed events could be lost.
- Not appropriate for financial transactions or critical data, but URL redirect analytics are inherently ephemeral and reconstructible.
