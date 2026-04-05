# Operational Runbook

This document defines response procedures for each alert and general incident handling.

## Alert: ServiceDown

**What it means:** A Flask application instance has been unreachable by Prometheus for over 15 seconds. The `/metrics` endpoint is not responding.

**Severity:** Critical

**Alert rule:**
```promql
up{job="flask-app"} == 0
```
Fires after 15 seconds of continuous failure (`for: 15s`).

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

## Metrics to Watch

These PromQL queries correspond to each alert type. Use them proactively to spot issues before alerts fire.

### ServiceDown -- Instance Availability

```promql
# Which instances are up/down right now
up{job="flask-app"}

# Number of healthy instances
count(up{job="flask-app"} == 1)

# Instance uptime trend (1 = up, 0 = down, over time)
up{job="flask-app"}[1h]
```

**What to look for:** Any instance showing `0` for more than a few seconds indicates a crash. If the value fluctuates (0, 1, 0, 1), the container is in a restart loop.

### HighErrorRate -- Error Monitoring

```promql
# Current error rate per instance (percentage)
(sum(rate(http_requests_total{status=~"5.."}[5m])) by (instance) / sum(rate(http_requests_total[5m])) by (instance)) * 100

# Error rate by endpoint (find which endpoint is failing)
(sum(rate(http_requests_total{status=~"5.."}[5m])) by (endpoint) / sum(rate(http_requests_total[5m])) by (endpoint)) * 100

# Total 5xx errors in the last hour
sum(increase(http_requests_total{status=~"5.."}[1h]))

# 4xx errors by endpoint (client errors, not our fault but worth watching)
sum(rate(http_requests_total{status=~"4.."}[5m])) by (endpoint)
```

**What to look for:** Error rate above 1% warrants investigation. Above 5% is degraded service. Above 10% triggers the alert. Check if errors are concentrated on one endpoint or spread across all.

### HighLatency -- Performance Monitoring

```promql
# p95 latency across all endpoints
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# p95 latency per endpoint (identify the slow one)
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# p99 latency (worst-case for 1% of requests)
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Average request duration per endpoint
sum(rate(http_request_duration_seconds_sum[5m])) by (endpoint) / sum(rate(http_request_duration_seconds_count[5m])) by (endpoint)

# Cache hit ratio (low ratio = high DB load = high latency)
sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
```

**What to look for:** p95 above 1 second is elevated. Above 2 seconds triggers the alert. Check cache hit ratio first -- if it dropped, Redis may be down. Check per-endpoint latency to isolate the bottleneck.

### HighMemoryUsage -- Resource Monitoring

```promql
# Memory usage per instance (in MB)
process_resident_memory_bytes / 1024 / 1024

# Memory growth rate (MB per hour -- detect leaks)
deriv(process_resident_memory_bytes[1h]) / 1024 / 1024 * 3600

# Predicted memory usage in 6 hours (linear extrapolation)
process_resident_memory_bytes + deriv(process_resident_memory_bytes[1h]) * 6 * 3600
```

**What to look for:** Memory above 200MB per instance is elevated. Above 512MB triggers the alert. Check `deriv()` for positive trends -- a consistently growing memory footprint indicates a leak.

---

## Recovery Verification Checklists

After resolving each alert type, verify full recovery using these checklists.

### After ServiceDown Resolution

- [ ] `docker compose ps` shows all 3 app instances as `Up`
- [ ] `curl http://localhost/health` returns `{"status": "ok", "database": "connected"}`
- [ ] Each instance responds individually:
  ```bash
  docker compose exec app1 curl -s http://localhost:5000/health
  docker compose exec app2 curl -s http://localhost:5000/health
  docker compose exec app3 curl -s http://localhost:5000/health
  ```
- [ ] Prometheus targets page (`http://localhost:9090/targets`) shows all 3 targets as UP
- [ ] Grafana Instance Health panel shows all instances green
- [ ] `docker inspect <container-id> --format='{{.RestartCount}}'` is not increasing

### After HighErrorRate Resolution

- [ ] Error rate query returns < 1%:
  ```bash
  curl -s 'http://localhost:9090/api/v1/query?query=(sum(rate(http_requests_total{status=~"5.."}[5m]))/sum(rate(http_requests_total[5m])))*100'
  ```
- [ ] Test each endpoint type:
  ```bash
  curl -s http://localhost/health                    # GET health
  curl -s http://localhost/users?per_page=1          # GET list
  curl -s http://localhost/urls?per_page=1           # GET list
  curl -s -X POST http://localhost/urls \
    -H "Content-Type: application/json" \
    -d '{"url":"https://example.com/recovery-test"}' # POST create
  ```
- [ ] No new errors in application logs:
  ```bash
  docker compose logs --tail=20 app1 app2 app3 | grep -i error
  ```
- [ ] Database is accessible:
  ```bash
  docker compose exec db psql -U postgres -d hackathon_db -c "SELECT count(*) FROM urls;"
  ```

### After HighLatency Resolution

- [ ] p95 latency is below 2 seconds:
  ```bash
  curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[5m]))by(le))'
  ```
- [ ] Cache hit ratio is above 50%:
  ```bash
  curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(cache_hits_total[5m]))/(sum(rate(cache_hits_total[5m]))+sum(rate(cache_misses_total[5m])))'
  ```
- [ ] Redis is responding:
  ```bash
  docker compose exec redis redis-cli ping
  ```
- [ ] No long-running queries in PostgreSQL:
  ```bash
  docker compose exec db psql -U postgres -d hackathon_db -c \
    "SELECT pid, state, query, now() - query_start AS duration FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '1 second';"
  ```
- [ ] Redirect latency is back to normal (test a known short code):
  ```bash
  time curl -s -o /dev/null -w "%{time_total}\n" http://localhost/$(curl -s http://localhost/urls?per_page=1 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['short_code'])")
  ```

### After HighMemoryUsage Resolution

- [ ] Memory per instance is below 200MB:
  ```bash
  docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}"
  ```
- [ ] Host memory has headroom:
  ```bash
  free -h
  ```
- [ ] Swap is available and not full:
  ```bash
  swapon --show
  ```
- [ ] No containers in OOM-killed state:
  ```bash
  docker ps -a --filter "status=exited" --format "{{.Names}}: exit {{.Status}}"
  ```

---

## Communication Protocol

### Who to Notify

| Severity | Who | How | When |
|----------|-----|-----|------|
| Critical (ServiceDown, complete outage) | On-call engineer | Discord alert (automatic) + direct message | Immediately |
| Warning (HighErrorRate, HighLatency) | On-call engineer | Discord alert (automatic) | Within 15 minutes |
| Informational (degraded but functional) | Team channel | Manual Discord message | Within 1 hour |
| Post-incident | All stakeholders | Written post-incident report | Within 24 hours |

### Escalation Timeline

| Time Since Detection | Action |
|---------------------|--------|
| 0 minutes | Automated alert fires. On-call engineer acknowledges. |
| 5 minutes | Begin investigation using the relevant alert section above. |
| 15 minutes | If root cause not identified, escalate to second engineer. |
| 30 minutes | If not mitigated, consider full stack restart as temporary measure. |
| 1 hour | If still unresolved, escalate to team lead. Consider reverting last deployment. |
| 2 hours | Formal incident declared. Continuous status updates every 30 minutes. |

### Status Update Template

Post this to the team Discord channel during active incidents:

```
**Incident Update -- [timestamp]**
Status: Investigating / Mitigating / Monitoring / Resolved
Alert: [alert name]
Impact: [what users experience]
Root cause: [known / investigating]
Next steps: [what we are doing next]
ETA to resolution: [time estimate or "unknown"]
```

---

## General Incident Response Process

### 1. Detect

Alerts arrive via the webhook receiver (with optional Discord forwarding if `DISCORD_WEBHOOK_URL` is configured). Check:
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
- Run the appropriate Recovery Verification Checklist from above.

### 6. Post-Incident

Fill out the Post-Incident Review template below within 24 hours of resolution.

---

## Post-Incident Review Template

Copy this template for each incident and fill it out after resolution.

```markdown
# Post-Incident Review: [Incident Title]

**Date:** YYYY-MM-DD
**Duration:** [start time] to [end time] ([total duration])
**Severity:** Critical / Warning
**Author:** [name]

## Timeline

| Time (UTC) | Event |
|------------|-------|
| HH:MM | Alert fired: [alert name] |
| HH:MM | On-call engineer acknowledged |
| HH:MM | Investigation started |
| HH:MM | Root cause identified: [brief description] |
| HH:MM | Mitigation applied: [what was done] |
| HH:MM | Service restored |
| HH:MM | Alert resolved |

## Impact

- **Users affected:** [number or description]
- **Requests failed:** [count or percentage]
- **Data loss:** [none / description of what was lost]
- **Duration of user-visible impact:** [time]

## Root Cause

[2-3 sentences describing the technical root cause. Not symptoms, not mitigation
-- the actual reason the failure occurred.]

## Detection

- **How was it detected?** Automated alert / Manual observation / User report
- **Time to detection (TTD):** [time from failure to detection]
- **Was the alerting effective?** Yes / No. If no, what should change?

## Resolution

- **Time to mitigation (TTM):** [time from detection to service restored]
- **Time to resolution (TTR):** [time from detection to root cause fixed]
- **What fixed it?** [specific commands or changes]

## What Went Well

- [bullet point]
- [bullet point]

## What Went Wrong

- [bullet point]
- [bullet point]

## Action Items

| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
| [action] | [name] | P0/P1/P2 | YYYY-MM-DD |

## Lessons Learned

[What should we do differently next time? What process or technical changes
would prevent this incident or reduce its impact?]
```
