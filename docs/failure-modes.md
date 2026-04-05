# Failure Mode Analysis

This document catalogs what happens when each system component fails, the impact on the service, and how the system recovers.

---

## PostgreSQL Failure

### What Happens

When PostgreSQL becomes unavailable (crash, OOM, network partition):

1. **All write operations fail immediately.** Creating URLs, creating users, updating records, and logging events all return 500 errors.
2. **Redirect cache hits continue to work.** If the URL is in Redis, the redirect succeeds. However, the event INSERT for the redirect will fail -- the redirect still returns 302 to the client, but the analytics event is lost.
3. **Redirect cache misses fail.** The database lookup raises an exception, returning 500.
4. **Health endpoint returns degraded:**
   ```json
   {"status": "degraded", "database": "disconnected"}
   ```
5. **List and detail endpoints fail** with 500 errors.

### Impact Assessment

| Endpoint | Impact |
|---|---|
| `GET /:short_code` (cache hit) | Works (302), but event not recorded |
| `GET /:short_code` (cache miss) | Fails (500) |
| `POST /urls` | Fails (500) |
| `POST /users` | Fails (500) |
| `GET /urls`, `GET /users` | Fails (500) |
| `PUT`, `DELETE` operations | Fails (500) |
| `GET /health` | Returns 200 with `"status": "degraded"` |
| `GET /metrics` | Works (Prometheus metrics are in-process) |

**Data loss risk:** Redirect events that occur during the outage (on cached URLs) are permanently lost. No retry or buffering mechanism exists. URL and user data in PostgreSQL is durable (WAL + fsync) up to the moment of crash.

### Recovery Behavior

- Docker restart policy (`unless-stopped`) will restart PostgreSQL if the process crashes.
- The `healthcheck` (runs `pg_isready` every 5 seconds) determines when PostgreSQL is available again.
- Flask app instances reconnect automatically on the next request via `db.connect(reuse_if_open=True)` in the `before_request` hook.
- No manual intervention needed for recovery, but lost events during the outage are not recoverable.

### Estimated Recovery Time

- Container crash + Docker restart: 5-15 seconds
- PostgreSQL crash recovery (WAL replay): 5-30 seconds depending on write volume
- Total: 10-45 seconds

---

## Redis Failure

### What Happens

When Redis becomes unavailable:

1. **All redirect lookups fall through to PostgreSQL.** The `_get_redis()` helper returns `None`, and all Redis operations silently fail (wrapped in try/except).
2. **Redirect latency increases** from ~5-15ms (cache hit) to ~20-50ms (database query).
3. **Cache invalidation on update/delete is silently skipped** (no-op when Redis is down).
4. **No error responses to clients.** The application gracefully degrades.

### Impact Assessment

| Endpoint | Impact |
|---|---|
| `GET /:short_code` | Works, but slower (all DB lookups) |
| `POST /urls` | No impact (creates don't use cache) |
| `PUT /urls/:id` | Works, cache invalidation silently skipped |
| `DELETE /urls/:id` | Works, cache invalidation silently skipped |
| All other endpoints | No impact |

**Data loss risk:** None. Redis is a cache; all authoritative data is in PostgreSQL.

### Recovery Behavior

- Docker restart policy restarts the Redis container.
- The `healthcheck` (runs `redis-cli ping` every 5 seconds) determines when Redis is available.
- The `_redis_client` singleton in `app/cache.py` will be `None` after a failure. On the next call to `get_redis()`, it attempts reconnection.
- After Redis restarts, the cache is empty. It repopulates on demand as redirects come in (cold start).

### Estimated Recovery Time

- Container restart: 1-3 seconds
- Cache warm-up: Gradual over 300 seconds (one TTL cycle) as redirects repopulate the cache

---

## Flask Instance Failure

### What Happens

When one of the three Flask+Gunicorn instances crashes:

1. **Nginx detects the failure** when the upstream connection is refused or times out (10-second connect timeout).
2. **Nginx routes subsequent requests to the remaining healthy instances.** The failed instance is temporarily removed from the pool.
3. **Overall capacity drops by approximately 33%** (from 36 handlers to 24).
4. **Prometheus shows the instance as DOWN** (`up{instance="appN:5000"} == 0`).
5. **ServiceDown alert fires** after 1 minute.

### Impact Assessment

| Scenario | Impact |
|---|---|
| 1 of 3 instances down | ~33% capacity reduction. No user-visible errors if remaining capacity is sufficient. |
| 2 of 3 instances down | ~66% capacity reduction. Likely increased latency under load. |
| All 3 instances down | Complete outage. Nginx returns 502 Bad Gateway. |

**Data loss risk:** None. Flask instances are stateless. All state is in PostgreSQL and Redis.

### Recovery Behavior

- Docker restart policy restarts the crashed container.
- The `HEALTHCHECK` in the Dockerfile (polls `/health` every 30 seconds) monitors the instance.
- Gunicorn's master process will restart a failed worker automatically (worker-level recovery).
- If the entire container crashes, Docker restarts it within 1-5 seconds.
- Nginx will start routing to the instance again once it accepts connections.

### Estimated Recovery Time

- Gunicorn worker crash: <1 second (master restarts the worker)
- Container crash + Docker restart: 5-15 seconds (including Gunicorn startup)

---

## Nginx Failure

### What Happens

When the Nginx container crashes:

1. **Complete service outage.** All client requests fail because Nginx is the only entry point on port 80.
2. **Flask instances are still running** and healthy, but unreachable from outside.
3. **Prometheus can still scrape Flask instances** directly (it connects to `appN:5000`, not through Nginx).
4. **No alerts fire for this specific failure** (Prometheus monitors Flask, not Nginx). The ServiceDown alert will NOT fire because Flask is still up.

### Impact Assessment

| Impact | Severity |
|---|---|
| All client traffic | Fails (connection refused on port 80) |
| Monitoring | Continues normally |
| Data integrity | No risk |

**Data loss risk:** None. Nginx has no state.

### Recovery Behavior

- Docker restart policy restarts Nginx within 1-5 seconds.
- No warm-up needed -- Nginx is immediately ready to proxy after startup.

### Estimated Recovery Time

- Container restart: 1-3 seconds

### Detection Gap

Nginx failure is not monitored by the current Prometheus configuration. To detect it, add:
1. An external uptime monitor (e.g., UptimeRobot) that polls `http://<public-ip>/nginx-health`
2. Or add the Nginx stub status exporter to Prometheus

---

## Prometheus Failure

### What Happens

When Prometheus crashes:

1. **No metrics are collected.** Grafana dashboards show gaps in data.
2. **Alert evaluation stops.** No alerts will fire for any condition (ServiceDown, HighErrorRate, etc.).
3. **The application continues to function normally.** Prometheus is a pull-based observer; its absence does not affect the application.
4. **The `/metrics` endpoint on Flask still works** and accumulates counters. When Prometheus recovers, it resumes scraping from the current counter values (it cannot retroactively fill the gap).

### Impact Assessment

| Impact | Severity |
|---|---|
| Application functionality | No impact |
| Dashboards | Data gap for the outage period |
| Alerting | Blind for the outage period |
| Metrics data | Permanent gap (not recoverable) |

**Data loss risk:** Prometheus time-series data for the outage window is permanently lost. Metric counters in the Flask process continue incrementing, but Prometheus won't have intermediate data points.

### Recovery Behavior

- Docker restart policy restarts Prometheus.
- On recovery, Prometheus loads its existing TSDB data (up to 7 days retention).
- It resumes scraping all targets within one scrape interval (10 seconds).
- Grafana dashboards automatically reconnect (Prometheus is the configured datasource).

### Estimated Recovery Time

- Container restart: 5-10 seconds (TSDB recovery may add time)

---

## Grafana Failure

### What Happens

When Grafana crashes:

1. **Dashboards are unavailable.** The Grafana web UI is unreachable.
2. **No impact on the application, metrics collection, or alerting.** Grafana is purely a visualization layer.
3. **Prometheus continues collecting metrics and evaluating alert rules.**
4. **Alertmanager continues routing alerts.**

### Impact Assessment

| Impact | Severity |
|---|---|
| Application functionality | No impact |
| Metrics collection | No impact |
| Alerting | No impact |
| Dashboard visibility | Unavailable |

**Data loss risk:** None. Grafana dashboard definitions are provisioned from files. User-created dashboards are stored in the `grafana_data` Docker volume.

### Recovery Behavior

- Docker restart policy restarts Grafana.
- Dashboards are auto-provisioned from `grafana/dashboards/url-shortener.json` on startup.
- The Prometheus datasource is auto-provisioned from `grafana/provisioning/datasources/prometheus.yml`.

### Estimated Recovery Time

- Container restart: 5-10 seconds

---

## Alertmanager Failure

### What Happens

When Alertmanager crashes:

1. **Alert notifications stop.** Discord messages are not sent.
2. **Prometheus continues evaluating alert rules** and shows alerts as FIRING in its own UI (`http://localhost:9090/alerts`).
3. **The application, metrics, and dashboards are unaffected.**

### Impact Assessment

| Impact | Severity |
|---|---|
| Application functionality | No impact |
| Alert evaluation | Continues (Prometheus) |
| Alert notification delivery | Stops |
| Dashboard visibility | No impact |

**Data loss risk:** Alerts that fire during the outage are evaluated by Prometheus but not delivered. Once Alertmanager recovers, Prometheus will resend any alerts that are still in the FIRING state.

### Recovery Behavior

- Docker restart policy restarts Alertmanager.
- Prometheus will reconnect and push any pending/active alerts.

### Estimated Recovery Time

- Container restart: 1-3 seconds

---

## Node Exporter Failure

### What Happens

When the Node Exporter container crashes:

1. **Host-level metrics (CPU, RAM, disk, network) stop being collected.** Prometheus shows the node-exporter target as DOWN.
2. **Infrastructure alert rules that depend on Node Exporter metrics stop evaluating correctly.** HostHighCpuUsage, HostHighMemoryUsage, HostDiskSpaceLow, and HostNetworkErrors alerts will not fire.
3. **The NodeExporterDown alert fires** after 30 seconds.
4. **No impact on the application, other metrics, or application-level alerts.**

### Impact Assessment

| Impact | Severity |
|---|---|
| Application functionality | No impact |
| Application metrics | No impact |
| Application alerts | No impact |
| Host metrics | Unavailable |
| Infrastructure alerts | Blind for the outage period |

**Data loss risk:** Host metrics for the outage window are permanently lost.

### Recovery Behavior

- Docker restart policy restarts the Node Exporter container.
- Prometheus resumes scraping within one scrape interval (15 seconds).

### Estimated Recovery Time

- Container restart: 1-3 seconds

---

## Webhook Receiver Failure

### What Happens

When the Webhook Receiver container crashes:

1. **Alert notifications stop being logged and forwarded.** Alertmanager will attempt to send alerts to the webhook receiver but receive connection errors.
2. **Prometheus continues evaluating alert rules** and shows alerts as FIRING in its own UI.
3. **Alertmanager continues grouping alerts** and will retry delivery.
4. **The application, metrics collection, and dashboards are unaffected.**
5. **If Discord forwarding is configured, Discord notifications also stop.**

### Impact Assessment

| Impact | Severity |
|---|---|
| Application functionality | No impact |
| Alert evaluation | Continues (Prometheus) |
| Alert notification delivery | Stops (Alertmanager retries) |
| Alert logging | Stops (local log and evidence files not written) |
| Discord forwarding | Stops (if configured) |
| Dashboard visibility | No impact |

**Data loss risk:** Alerts that fire during the outage are evaluated by Prometheus and queued by Alertmanager. Once the webhook receiver recovers, Alertmanager will resend any alerts that are still in the FIRING state. Alerts that fired and resolved during the outage window may not be logged.

### Recovery Behavior

- Docker restart policy restarts the webhook receiver.
- Alertmanager will retry delivery of pending alerts.
- The evidence directory is mounted as a Docker volume, so previously written files persist.

### Estimated Recovery Time

- Container restart: 1-3 seconds

---

## Cascading Failure Scenarios

### Scenario 1: PostgreSQL Crash Under Load

1. PostgreSQL crashes (OOM, disk full, or killed).
2. All Flask instances start returning 500 errors for database operations.
3. Redis continues serving cached redirects for up to 300 seconds.
4. After 300 seconds, cache entries expire and all redirects fail.
5. HighErrorRate alert fires after 2 minutes.
6. Docker restarts PostgreSQL (5-15 seconds).
7. Flask instances reconnect automatically.
8. Cache repopulates over the next few minutes.

**Total impact window:** 5-15 seconds (PostgreSQL restart) + gradual cache recovery

### Scenario 2: Host OOM (Out of Memory)

1. System runs out of memory. The Linux OOM killer activates.
2. Containers are killed in unpredictable order (usually the largest memory consumer first).
3. If PostgreSQL is killed, Scenario 1 applies.
4. If a Flask instance is killed, the other two handle traffic with reduced capacity.
5. Docker restart policy attempts to restart killed containers.
6. If the host is severely memory-constrained, containers may enter a kill-restart loop.

**Mitigation:** Swap space absorbs temporary spikes. For sustained OOM, reduce container count or upgrade the droplet.

### Scenario 3: Disk Full

1. PostgreSQL cannot write WAL or new data. All writes fail.
2. Event logging fails, URL creation fails, user creation fails.
3. Reads may continue working from existing data.
4. Prometheus TSDB cannot write new samples.
5. Docker cannot write container logs.

**Mitigation:** Monitor disk usage. Clean Docker resources:
```bash
docker system prune -f
```

### Scenario 4: Network Partition (Container Network)

1. If the Docker bridge network fails, containers cannot communicate.
2. All inter-service communication fails: Flask cannot reach PostgreSQL or Redis, Nginx cannot reach Flask, Prometheus cannot scrape.
3. This is functionally equivalent to a complete outage.

**Mitigation:** Restart Docker:
```bash
sudo systemctl restart docker
```

---

## Recovery Priority Order

When multiple components fail simultaneously, restore in this order:

1. **PostgreSQL** -- All other services depend on the database.
2. **Redis** -- Restores cache, reduces database load.
3. **Flask instances** -- Restores application availability.
4. **Nginx** -- Restores external access.
5. **Prometheus** -- Restores monitoring.
6. **Alertmanager** -- Restores alert routing.
7. **Webhook Receiver** -- Restores alert logging and Discord forwarding.
8. **Node Exporter** -- Restores host-level metrics.
9. **Grafana** -- Restores dashboards.
