# Operational Runbook

This document defines response procedures for each alert and general incident handling.

## Alert: ServiceDown

**What it means:** A Flask application instance has been unreachable by Prometheus for over 1 minute. The `/metrics` endpoint is not responding.

**Severity:** Critical

**Alert rule:**
```promql
up{job="flask-app"} == 0
```
Fires after 1 minute of continuous failure.

### Immediate Actions

1. **Identify which instance is down:**
   ```bash
   docker compose ps
   ```
   Look for containers not showing `Up` status.

2. **Check the container logs:**
   ```bash
   docker compose logs --tail=100 <service-name>
   ```
   Look for Python tracebacks, OOM kills (exit code 137), or startup errors.

3. **Check if Docker auto-restart is working:**
   ```bash
   docker inspect <container-id> --format='{{.State.Status}} {{.State.ExitCode}} {{.RestartCount}}'
   ```
   With `restart: unless-stopped`, Docker should be restarting the container automatically.

4. **If the container is in a restart loop, manually restart:**
   ```bash
   docker compose restart <service-name>
   ```

5. **If the container won't start at all:**
   ```bash
   # Rebuild the image
   docker compose up --build -d <service-name>
   ```

### Root Cause Investigation

- **Exit code 137:** OOM killed. Check `free -h` and `docker stats`. See [HighMemoryUsage](#alert-highmemoryusage).
- **Exit code 1:** Application error. Check logs for the traceback.
- **No exit, container running but /metrics not responding:** The Gunicorn workers may be stuck. Check for deadlocks or hung database connections:
  ```bash
  docker compose exec db psql -U postgres -d hackathon_db -c \
    "SELECT pid, state, query, now() - query_start AS duration FROM pg_stat_activity WHERE state != 'idle';"
  ```

### Escalation

If a single instance is down but the other two are handling traffic, this is degraded but not a full outage. Nginx will stop routing to the dead instance automatically.

If all three instances are down, the service is fully unavailable. Escalate immediately -- check if the database or the host itself is the root cause.

---

## Alert: HighErrorRate

**What it means:** More than 10% of HTTP responses from a Flask instance have been 5xx status codes over the last 5 minutes, sustained for at least 2 minutes.

**Severity:** Warning

**Alert rule:**
```promql
(
  sum(rate(http_requests_total{status=~"5.."}[5m])) by (instance)
  /
  sum(rate(http_requests_total[5m])) by (instance)
) > 0.10
```

### Immediate Actions

1. **Check which endpoints are producing errors:**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~"5.."}[5m]))by(endpoint)' | python3 -m json.tool
   ```

2. **Check application logs for the errors:**
   ```bash
   docker compose logs --tail=200 app1 app2 app3 | grep -i error
   ```

3. **Check database connectivity:**
   ```bash
   docker compose exec app1 python -c "
   from app.database import db
   db.connect(reuse_if_open=True)
   db.execute_sql('SELECT 1')
   print('DB OK')
   "
   ```

4. **Check the health endpoint:**
   ```bash
   curl http://localhost/health
   ```
   If `database: disconnected`, the database is the problem.

### Root Cause Investigation

| Error Pattern | Likely Cause |
|---|---|
| All endpoints returning 500 | Database down or connection pool exhausted |
| Only POST endpoints returning 500 | Database write issue (disk full, constraint violation) |
| Only redirect endpoint returning 500 | Redis-related error in event logging |
| Intermittent 500s across endpoints | Gunicorn worker timeout, restart loop |

**Check database disk space:**
```bash
docker compose exec db psql -U postgres -c "SELECT pg_database_size('hackathon_db');"
df -h  # Host disk
```

**Check connection count:**
```bash
docker compose exec db psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
```

### Escalation

If the error rate is climbing and the fixes above don't resolve it, restart all app instances:
```bash
docker compose restart app1 app2 app3
```

If that doesn't help, restart the database:
```bash
docker compose restart db
# Wait for health check
docker compose restart app1 app2 app3
```

---

## Alert: HighLatency

**What it means:** The 95th percentile of HTTP request latency exceeds 2 seconds over the last 5 minutes, sustained for at least 3 minutes.

**Severity:** Warning

**Alert rule:**
```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, instance)) > 2.0
```

### Immediate Actions

1. **Check if Redis is healthy:**
   ```bash
   docker compose exec redis redis-cli ping
   docker compose exec redis redis-cli info memory
   ```
   If Redis is down, all redirects become cache misses and hit the database.

2. **Check cache hit ratio:**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(cache_hits_total[5m]))/(sum(rate(cache_hits_total[5m]))+sum(rate(cache_misses_total[5m])))' | python3 -m json.tool
   ```
   A ratio below 0.5 indicates poor caching -- either Redis is down or the working set is larger than the TTL window.

3. **Check per-endpoint latency:**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[5m]))by(le,endpoint))' | python3 -m json.tool
   ```

4. **Check database query performance:**
   ```bash
   docker compose exec db psql -U postgres -d hackathon_db -c \
     "SELECT pid, state, query, now() - query_start AS duration FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC LIMIT 10;"
   ```

### Root Cause Investigation

| Scenario | Root Cause | Fix |
|---|---|---|
| Redis down, redirect p95 high | All lookups hitting DB | `docker compose restart redis` |
| Redis OK, redirect p95 high | DB slow (missing index, lock contention) | Check `pg_stat_activity` for long queries |
| List endpoints slow | Large result sets, no pagination | Ensure clients use `per_page` parameter |
| All endpoints slow | CPU saturation | Check `top` on host, consider scaling |

### Escalation

If latency is above 5 seconds sustained, the system is effectively unusable for real-time URL shortening. Reduce load (stop non-critical traffic) and investigate the bottleneck.

---

## Alert: HighMemoryUsage

**What it means:** A Flask process's resident memory exceeds 512MB for more than 5 minutes.

**Severity:** Warning

**Alert rule:**
```promql
process_resident_memory_bytes / 1024 / 1024 > 512
```

### Immediate Actions

1. **Check memory across all containers:**
   ```bash
   docker stats --no-stream
   ```

2. **Check host memory:**
   ```bash
   free -h
   ```

3. **Check if swap is active:**
   ```bash
   swapon --show
   ```

4. **If approaching OOM, restart the high-memory instance:**
   ```bash
   docker compose restart <service-name>
   ```

### Root Cause Investigation

- **Memory leak in application code:** Check if memory grows unbounded over time. Restart the affected instance and monitor.
- **Large response payloads:** If a query returns massive result sets, memory can spike. Check for requests without pagination.
- **Gunicorn worker accumulation:** If `--max-requests` is not set, long-lived workers can accumulate memory. Consider adding:
  ```dockerfile
  CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--max-requests", "1000", "--max-requests-jitter", "100", ...]
  ```

### Escalation

If memory is critically low and containers are being OOM-killed:

1. Add swap immediately (see [deployment.md](deployment.md))
2. Reduce Gunicorn workers from 4 to 2
3. Consider removing one Flask instance (2 instead of 3)

---

## General Incident Response Process

### 1. Detect

Alerts arrive via Discord (Alertmanager webhook). Check:
- Alert name and severity
- Which instance is affected
- When it started firing

### 2. Triage

| Severity | Response Time | Impact |
|---|---|---|
| Critical | Immediate | Service outage, data loss risk |
| Warning | Within 15 minutes | Degraded performance or partial failure |

### 3. Investigate

```bash
# Overview of all services
docker compose ps

# Resource usage
docker stats --no-stream

# Host resources
free -h && df -h && uptime

# Recent logs across all services
docker compose logs --tail=50
```

### 4. Mitigate

Priority is to restore service. Fix the root cause later.

| Situation | Mitigation |
|---|---|
| Single instance down | Verify Nginx is routing around it. Restart the instance. |
| All instances down | Restart all: `docker compose restart app1 app2 app3` |
| Database down | `docker compose restart db`, then restart apps |
| Redis down | `docker compose restart redis` (apps degrade gracefully) |
| Host OOM | Add swap, reduce workers, restart containers |
| Disk full | Clean Docker: `docker system prune -f`, check logs |

### 5. Resolve

Once service is restored:
- Verify health: `curl http://localhost/health`
- Verify metrics: check Grafana dashboard
- Verify the alert resolves in Alertmanager

### 6. Post-Incident

Document:
- What alerted and when
- Root cause
- Mitigation steps taken
- Time to detection, time to mitigation, time to resolution
- Preventive measures for next time
