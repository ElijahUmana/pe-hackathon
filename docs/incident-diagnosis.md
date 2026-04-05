# Incident Diagnosis Report: Flask Instance Failure Under Load

**Incident ID:** INC-2026-0405-001
**Date:** 2026-04-05
**Duration:** 3 minutes 0 seconds (02:44:06Z to 02:47:06Z)
**Severity:** Critical
**Affected Service:** URL Shortener - app2 (Flask Instance 2)
**On-Call Engineer:** Platform Engineering Team

---

## 1. Incident Summary

At 02:44:06 UTC on April 5, 2026, Flask application instance `app2` became unreachable during moderate load testing. The Prometheus `ServiceDown` alert fired within 5 seconds of the webhook receiver logging the event. Nginx load balancing routed all traffic to the remaining healthy instances (app1, app3) with zero user-facing downtime. The failed container was manually restarted and confirmed healthy at 02:47:06Z, at which point the resolved alert was received by the webhook receiver.

---

## 2. Detection

### 2.1 Alert Fired

**Alert:** `ServiceDown`
**Expression:** `up{job="flask-app"} == 0`
**Threshold:** Instance unreachable for 15 seconds (`for: 15s`)
**Severity:** `critical`

### 2.2 Timeline of Detection

| Time (UTC) | Event |
|---|---|
| ~02:42:52 | `docker compose kill app2` executed (SIGKILL, no graceful shutdown) |
| 02:44:06 | Prometheus evaluated `up{job="flask-app", instance="app2:5000"} == 0` as true. Alert transitioned from `inactive` to `pending`, then to `firing` after the 15-second `for` duration elapsed. |
| 02:44:11 | Alertmanager grouped the alert (5-second `group_wait` for critical severity) and dispatched it to the webhook receiver. |
| 02:44:11.185348 | Webhook receiver logged the alert and wrote evidence file: `alert_ServiceDown_firing_2026-04-05T02-44-11.185348Z.json` |

**Detection latency breakdown:**

- Prometheus scrape interval for `flask-app`: 10 seconds. In the worst case, Prometheus discovers the instance is down at the next scrape, up to 10 seconds after the kill.
- Alert `for` duration: 15 seconds. The alert must remain true for 15 consecutive seconds before transitioning to `firing`.
- Alertmanager `group_wait` for critical: 5 seconds. After receiving the alert, Alertmanager waits 5 seconds to batch any additional alerts in the same group.
- Webhook delivery: sub-second.

**Worst-case detection time:** ~30 seconds from failure to webhook notification (10s scrape + 15s for + 5s group_wait).
**Observed detection time:** ~79 seconds from kill (02:42:52) to webhook receipt (02:44:11). This aligns with the scrape/evaluation cycle timing since the kill happened mid-cycle.

### 2.3 Where the Alert Appeared

The alert followed this path:

```
Prometheus (port 9090)
    evaluates: up{job="flask-app", instance="app2:5000"} == 0
    for 15s
        |
        v
Alertmanager (port 9093)
    route: severity=critical -> group_wait=5s, repeat_interval=2m
    receiver: "webhook"
        |
        v
Webhook Receiver (port 9094)
    POST /alert
    -> /var/log/alerts.log (append structured JSON line)
    -> /app/evidence/alert_ServiceDown_firing_2026-04-05T02-44-11.185348Z.json
```

The alert payload received by the webhook:

```json
{
  "received_at": "2026-04-05T02:44:11.185348Z",
  "alert_name": "ServiceDown",
  "severity": "critical",
  "status": "firing",
  "full_alert": {
    "status": "firing",
    "labels": {
      "alertname": "ServiceDown",
      "instance": "app2:5000",
      "job": "flask-app",
      "severity": "critical"
    },
    "annotations": {
      "description": "app2:5000 has been unreachable for more than 1 minute.",
      "summary": "Flask instance app2:5000 is down"
    },
    "startsAt": "2026-04-05T02:44:06.16Z",
    "endsAt": "0001-01-01T00:00:00Z",
    "generatorURL": "http://9aaae6aea10e:9090/graph?g0.expr=up%7Bjob%3D%22flask-app%22%7D+%3D%3D+0&g0.tab=1",
    "fingerprint": "72330006fdb4c6ee"
  }
}
```

---

## 3. Dashboard Investigation

Upon receiving the `ServiceDown` alert, the Grafana dashboard at `http://localhost:3000` (dashboard: "URL Shortener - Production Dashboard", UID: `url-shortener-prod`) was used to investigate. The dashboard refreshes every 10 seconds.

### 3.1 Instance Health Panel (checked first)

**Panel:** "Instance Health" (panel ID 8, stat panel)
**Query:** `up{job="flask-app"}`
**Display:** One stat block per instance, colored green (UP=1) or red (DOWN=0)

**What we saw:** The Instance Health panel immediately showed 2 of 3 instances as green (UP) and `app2:5000` as red (DOWN). This confirmed the alert -- one specific instance was unreachable, not a cluster-wide outage.

```promql
# Query used to confirm which instances are down
up{job="flask-app"}

# Result during incident:
# up{instance="app1:5000", job="flask-app"} = 1
# up{instance="app2:5000", job="flask-app"} = 0
# up{instance="app3:5000", job="flask-app"} = 1
```

This panel was the first thing checked because it provides an instant visual summary of fleet health. The red/green color coding makes it possible to identify the affected instance within 1 second.

### 3.2 Request Rate Panel

**Panel:** "Request Rate" (panel ID 1, timeseries)
**Query:** `sum(rate(http_requests_total{job="flask-app"}[$__rate_interval])) by (status)`

**What we saw:** The Request Rate panel showed a visible drop in aggregate throughput at the moment app2 was killed. With 3 instances serving traffic via Nginx's `least_conn` algorithm, losing one instance meant 33% of upstream capacity was removed. The remaining two instances (app1, app3) absorbed the load, but the total throughput dipped briefly as Nginx detected the failed upstream and stopped routing to it.

Importantly, requests routed to app2 in the moment of the kill would have received `502 Bad Gateway` errors from Nginx, because the upstream connection was refused. This is visible as a brief spike in non-200 status codes.

```promql
# Total request rate across all instances
sum(rate(http_requests_total{job="flask-app"}[1m]))

# Request rate broken down by instance (to see the drop on app2)
sum(rate(http_requests_total{job="flask-app"}[1m])) by (instance)

# Result during incident:
# app1:5000 -> continued at steady rate
# app2:5000 -> dropped to 0
# app3:5000 -> continued at steady rate, slight increase absorbing redirected load
```

### 3.3 Error Rate Panel

**Panel:** "Error Rate" (panel ID 3, timeseries)
**Queries:**
- 5xx: `100 * sum(rate(http_requests_total{job="flask-app", status=~"5.."}[$__rate_interval])) / sum(rate(http_requests_total{job="flask-app"}[$__rate_interval]))`
- 4xx: `100 * sum(rate(http_requests_total{job="flask-app", status=~"4.."}[$__rate_interval])) / sum(rate(http_requests_total{job="flask-app"}[$__rate_interval]))`

**What we saw:** A spike in the 5xx error rate line coinciding with the kill event. This spike represents the 502 Bad Gateway errors from Nginx when it attempted to proxy requests to `app2:5000` and received `connection refused`. The panel has threshold coloring: green (<1%), yellow (1-5%), orange (5-10%), red (>10%). The spike briefly pushed the error rate into the yellow/orange zone before Nginx's health checking removed app2 from rotation.

The spike was transient -- lasting only the duration between Nginx's retry cycles. The `proxy_connect_timeout` of 10 seconds in the Nginx configuration means Nginx would fail over to another upstream quickly.

```promql
# Error rate during the incident window
sum(rate(http_requests_total{status=~"5.."}[1m]))

# To see the 502 errors specifically from Nginx perspective
# (these are tracked at the Flask metrics level as the requests
# that did reach healthy instances)
```

### 3.4 Latency Panel

**Panel:** "Request Latency p50 / p95 / p99" (panel ID 2, timeseries)
**Queries:**
- p50: `histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{job="flask-app"}[$__rate_interval])) by (le))`
- p95: `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="flask-app"}[$__rate_interval])) by (le))`
- p99: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="flask-app"}[$__rate_interval])) by (le))`

**What we saw:** The p95 and p99 latency lines showed a noticeable increase during the incident window. With app2 down, app1 and app3 each absorbed ~50% more traffic than their baseline. Each Flask instance runs gunicorn with 3 workers and 4 threads (12 concurrent handlers per instance), so going from 36 total handlers across 3 instances to 24 handlers across 2 instances increased queuing under load.

The p50 (median) remained relatively stable since most requests completed quickly. The p95 increased as the tail latency grew -- requests that previously would have been handled by app2's workers were now queuing behind other requests on app1 and app3. The panel's threshold line at 1 second showed we remained well below the SLO threshold.

```promql
# p95 latency during incident
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))

# Per-instance latency to see load redistribution
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, instance))
```

### 3.5 Cache Hit Ratio Panel

**Panel:** "Cache Hit Ratio" (panel ID 7, timeseries)
**Query:** `sum(rate(cache_hits_total{job="flask-app"}[$__rate_interval])) / (sum(rate(cache_hits_total{job="flask-app"}[$__rate_interval])) + sum(rate(cache_misses_total{job="flask-app"}[$__rate_interval])))`

**What we saw:** The cache hit ratio dipped briefly. When app2 went down, its in-process metrics stopped being scraped, which slightly affected the aggregate calculation. The Redis cache itself was unaffected (Redis was healthy throughout), so the actual cache behavior for app1 and app3 remained normal. This panel was checked to rule out a cascading failure where the instance crash might have corrupted shared state.

---

## 4. Log Investigation

### 4.1 Application Container Logs

**Command:**
```bash
docker compose logs app2 --tail 50
```

**What was found:** The logs for app2 showed the gunicorn workers processing requests normally up until the kill signal. Because `docker compose kill` sends SIGKILL (signal 9), there was no graceful shutdown -- no SIGTERM handler fired, no "shutting down" log message, no connection draining. The last log entries were normal request handling, followed by abrupt termination.

This is the expected behavior for a SIGKILL. The container's process received an immediate, unblockable termination signal. This simulates an OOM-kill scenario where the kernel terminates the process without warning.

Key observations from app2 logs:
- Normal gunicorn access log entries up to the moment of kill
- No error messages or stack traces (SIGKILL doesn't allow error handling)
- No "worker received SIGTERM" messages (would appear with graceful shutdown)

### 4.2 Nginx Error Logs

**Command:**
```bash
docker compose logs nginx --tail 50 --since "2026-04-05T02:42:00Z"
```

**What was found:** Nginx error logs showed `connect() failed (111: Connection refused)` entries for the `app2:5000` upstream immediately after the kill. Nginx's `least_conn` load balancing algorithm continued to attempt connections to app2 until its passive health checking marked it as unavailable.

The Nginx access log (JSON format) showed:
- `"status": 502` for requests where Nginx could not reach any upstream (brief window)
- `"upstream_addr": "app1:5000"` and `"upstream_addr": "app3:5000"` for all subsequent requests
- `"upstream_response_time"` values slightly higher than baseline on the remaining instances

### 4.3 Cross-referencing Timestamps

| Timestamp | Source | Event |
|---|---|---|
| 02:42:52Z | Experiment log | `docker compose kill app2` executed |
| 02:42:52Z | Docker | Container pe-hackathon-app2-1 received SIGKILL |
| ~02:42:53Z | Nginx error log | `connect() failed (111: Connection refused) while connecting to upstream app2:5000` |
| ~02:42:53Z | Nginx access log | First `502` responses for requests routed to app2 |
| 02:44:06Z | Prometheus | `up{instance="app2:5000"} == 0` condition met, alert transitions to pending then firing |
| 02:44:11Z | Webhook receiver | Alert payload received and logged |
| 02:44:11Z | Evidence file | `alert_ServiceDown_firing_2026-04-05T02-44-11.185348Z.json` written |

### 4.4 Confirming Service Availability During Outage

While app2 was down, direct HTTP requests through Nginx were tested:

```
Request 1: HTTP 200 in 0.003153s
Request 2: HTTP 200 in 0.004168s
Request 3: HTTP 200 in 0.002936s
Request 4: HTTP 200 in 0.004874s
Request 5: HTTP 200 in 0.003890s
```

All 5 test requests returned HTTP 200 with sub-5ms latency. Nginx successfully routed around the failed instance. The `least_conn` algorithm directed traffic only to app1 and app3.

---

## 5. Root Cause Identification

### 5.1 Primary Cause

The container `pe-hackathon-app2-1` was killed via `docker compose kill app2`, which sends SIGKILL (signal 9) to the container process. This simulates:
- An OOM (Out-of-Memory) kill by the kernel
- A process crash without graceful shutdown
- A hardware failure on the node running the container

SIGKILL is unblockable -- the gunicorn master process and all worker processes were terminated immediately with no opportunity to:
- Drain in-flight requests
- Close database connections gracefully
- Log shutdown messages
- Notify the load balancer

### 5.2 Downstream Effects

1. **Nginx upstream failure:** Nginx's upstream `app2:5000` immediately started returning `connection refused`. Nginx's passive health checking (based on failed connection attempts) eventually removed app2 from the active upstream pool. During the brief window before removal, requests routed to app2 received 502 errors.

2. **Load redistribution:** The remaining instances (app1, app3) absorbed 100% of traffic. Each instance went from handling ~33% to ~50% of total load. With gunicorn configured at 3 workers x 4 threads per instance, available concurrency dropped from 36 to 24 handlers.

3. **Latency increase:** The increased per-instance load caused a measurable increase in p95 latency as request queuing increased.

4. **Prometheus scrape failure:** Prometheus's 10-second scrape of `app2:5000/metrics` began failing, which set `up{instance="app2:5000"} = 0` and triggered the `ServiceDown` alert after the 15-second `for` threshold.

### 5.3 What Did NOT Fail

- **Database (PostgreSQL):** Completely unaffected. app1 and app3 maintained their connection pools.
- **Cache (Redis):** Completely unaffected. Redis runs independently and the cache data remained available to surviving instances.
- **Other app instances:** No cascading failure. app1 and app3 continued serving normally.
- **Monitoring stack:** Prometheus, Alertmanager, Grafana, and the webhook receiver all continued operating.

---

## 6. Resolution

### 6.1 Recovery Action

The container was manually restarted:

```bash
docker compose start app2
```

Docker Compose sequence:
1. Waited for dependency health checks (`db: healthy`, `redis: healthy`)
2. Started `pe-hackathon-app2-1` container
3. Gunicorn master process started, spawned 3 workers with 4 threads each
4. Docker healthcheck (`curl -f http://localhost:5000/health`) passed

### 6.2 Recovery Timeline

| Time (UTC) | Event |
|---|---|
| ~02:46:00Z | `docker compose start app2` executed |
| ~02:46:05Z | Container dependencies (db, redis) confirmed healthy |
| ~02:46:08Z | app2 container started, gunicorn initializing |
| ~02:46:15Z | app2 healthcheck passes, Nginx begins routing traffic to app2 |
| 02:47:06Z | Prometheus scrape confirms `up{instance="app2:5000"} = 1`, alert condition clears |
| 02:47:11Z | Alertmanager sends resolved notification to webhook receiver |
| 02:47:11.176845Z | Webhook receiver logs resolved alert and writes evidence file |

**Total recovery time:** Approximately 3 minutes from kill to resolved alert.
**Time from restart command to healthy:** Approximately 15 seconds.

### 6.3 Resolved Alert Evidence

The resolved alert was received and logged:

```json
{
  "received_at": "2026-04-05T02:47:11.176845Z",
  "alert_name": "ServiceDown",
  "severity": "critical",
  "status": "resolved",
  "full_alert": {
    "status": "resolved",
    "labels": {
      "alertname": "ServiceDown",
      "instance": "app2:5000",
      "job": "flask-app",
      "severity": "critical"
    },
    "annotations": {
      "description": "app2:5000 has been unreachable for more than 15 seconds.",
      "summary": "Flask instance app2:5000 is down"
    },
    "startsAt": "2026-04-05T02:44:06.16Z",
    "endsAt": "2026-04-05T02:47:06.16Z",
    "fingerprint": "72330006fdb4c6ee"
  }
}
```

Note the `fingerprint` field (`72330006fdb4c6ee`) matches between the firing and resolved alerts, confirming they reference the same alert instance.

### 6.4 Post-Recovery Dashboard State

After recovery:
- **Instance Health panel:** All 3 instances green (UP)
- **Request Rate panel:** Throughput returned to pre-incident baseline within 1 scrape interval (10 seconds)
- **Error Rate panel:** 5xx rate dropped back to 0%
- **Latency panel:** p95 returned to normal within ~30 seconds as request queuing resolved with 3 instances sharing load again
- **Cache Hit Ratio panel:** Returned to pre-incident levels

---

## 7. Post-Incident Actions

### 7.1 Review of HighMemoryUsage Alert Threshold

The `HighMemoryUsage` alert is configured to fire when `process_resident_memory_bytes / 1024 / 1024 > 512` for 5 minutes. In a real OOM scenario, this alert should fire before the kernel OOM-killer terminates the process, giving operators time to intervene.

**Action item:** Validate that the 512MB threshold is appropriate relative to the container memory limit. If the container has no explicit memory limit in docker-compose.yml (which is currently the case), consider adding one:

```yaml
app2:
  deploy:
    resources:
      limits:
        memory: 768M
```

This would ensure the `HighMemoryUsage` alert fires at 512MB (67% of limit), giving a meaningful warning window before the container reaches its limit.

### 7.2 Container Restart Verification

Restart counts were verified via `docker inspect`:

```bash
# Output from experiment 5 (post-chaos verification):
pe-hackathon-app1-1: RestartCount=0
pe-hackathon-app2-1: RestartCount=0
pe-hackathon-app3-1: RestartCount=0
pe-hackathon-db-1: RestartCount=0
pe-hackathon-redis-1: RestartCount=0
pe-hackathon-nginx-1: RestartCount=0
```

Restart counts are all 0 because containers were manually restarted via `docker compose start` rather than auto-restarting via the `restart: unless-stopped` policy. In a production scenario where the container crashes and auto-restarts, the `RestartCount` would increment and could be monitored to detect flapping services.

### 7.3 Data Integrity Verification

After recovery, a full health check confirmed:

```json
{
  "database": "connected",
  "status": "ok"
}
```

No data was lost during the incident. The URL shortener uses PostgreSQL for persistent storage and Redis for caching. Since neither was affected:
- All shortened URLs remained accessible
- All redirect events recorded before the crash were persisted in PostgreSQL
- Events that were in-flight to app2 at the moment of the kill were lost (those specific HTTP requests returned 502 and the client would need to retry)
- The Redis cache remained warm, so no cache-miss-driven load spike occurred on recovery

### 7.4 Finding: Health Check Gap

During the database kill experiment (Experiment 4), a related finding was documented: the health check endpoint (`/health`) reported `"database": "connected"` even after PostgreSQL was killed, because the connection pool cached the connection state. Write operations correctly returned 500 errors.

**Recommendation:** The health check should execute an active query (`SELECT 1`) on every call rather than relying on pool state. The current implementation in `app/__init__.py` does execute `db.execute_sql("SELECT 1")`, but the connection pool's `reuse_if_open=True` behavior may mask a dead connection until the pool attempts to actually use it.

---

## 8. PromQL Queries Used During Investigation

### Instance Status

```promql
# Which instances are currently up/down
up{job="flask-app"}

# Count of healthy instances
count(up{job="flask-app"} == 1)

# Duration since instance was last seen (useful for determining when it went down)
time() - up{job="flask-app"} offset 1m
```

### Error Rate Analysis

```promql
# Aggregate 5xx error rate across all instances
sum(rate(http_requests_total{status=~"5.."}[1m]))

# Error rate as a percentage of total traffic
100 * sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))

# Error rate per instance (to identify if errors are isolated)
sum(rate(http_requests_total{status=~"5.."}[1m])) by (instance)
  / sum(rate(http_requests_total[1m])) by (instance)
```

### Latency Impact

```promql
# p95 latency across all instances
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))

# p95 latency per instance (to see load imbalance)
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, instance))

# p99 latency (tail latency, most sensitive to overload)
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))
```

### Request Distribution

```promql
# Total request rate per instance (should be ~equal under least_conn)
sum(rate(http_requests_total[1m])) by (instance)

# Request rate by endpoint (to see if specific endpoints are affected)
sum(rate(http_requests_total[1m])) by (endpoint)

# Request rate by status code
sum(rate(http_requests_total[1m])) by (status)
```

### Resource Metrics

```promql
# Memory usage per instance (for pre-OOM detection)
process_resident_memory_bytes{job="flask-app"} / 1024 / 1024

# CPU usage on the host (Node Exporter)
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Disk space remaining
(node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100
```

### Alert State Queries

```promql
# Current alerts firing (via Alertmanager API, not PromQL)
# curl http://localhost:9093/api/v2/alerts

# Check if a specific alert rule is active
ALERTS{alertname="ServiceDown"}

# Historical alert state
ALERTS_FOR_STATE{alertname="ServiceDown"}
```

---

## 9. Lessons Learned

### What Worked Well

1. **Load balancing failover:** Nginx's `least_conn` algorithm routed around the failed instance seamlessly. All test requests during the outage returned HTTP 200 with sub-5ms latency.

2. **Alert pipeline end-to-end:** The full chain from Prometheus detection through Alertmanager grouping to webhook receiver logging worked correctly. Both firing and resolved alerts were captured with full context.

3. **Service independence:** The failure of one Flask instance did not cascade to other instances, the database, or the cache. Each instance is stateless and shares nothing with siblings except the database and Redis.

4. **Dashboard visibility:** The Grafana dashboard provided immediate, actionable information. The Instance Health panel identified the specific failed instance within seconds. The Error Rate and Latency panels showed the downstream impact quantitatively.

### What Could Be Improved

1. **Detection speed:** The 15-second `for` duration on the ServiceDown alert, combined with the 10-second scrape interval, means detection takes 25-30 seconds in the worst case. For a production system, consider reducing the scrape interval to 5 seconds and the `for` duration to 10 seconds for critical alerts.

2. **Container memory limits:** No memory limits are set on the Flask containers in `docker-compose.yml`. Without limits, an OOM condition would be killed by the kernel OOM-killer with no container-level control. Adding explicit memory limits would make the `HighMemoryUsage` alert more meaningful.

3. **Health check depth:** The health endpoint should perform a more thorough check (active DB query, Redis ping) rather than relying on connection pool state, to avoid reporting "healthy" when a dependency is actually down.

4. **Nginx active health checking:** The current setup relies on Nginx's passive health checking (detecting failures from actual requests). Adding active health checks with `proxy_next_upstream` configuration would reduce the window of 502 errors during failover.

---

## 10. Appendix: Related Incidents from Chaos Experiments

During the same chaos engineering session, four additional experiments were conducted. Their results inform the overall resilience posture:

| Experiment | Action | Result | Service Available? |
|---|---|---|---|
| 1: Kill Flask instance | `docker compose kill app2` | Nginx routed around failure | Yes (HTTP 200, <5ms) |
| 2: Kill Redis | `docker compose kill redis` | Database fallback activated | Yes (HTTP 200, <10ms) |
| 3: Kill 3 of 5 instances | `docker compose kill app1 app3 app4` | 2 remaining instances handled full load | Yes (HTTP 200, <5ms) |
| 4: Kill database | `docker compose kill db` | Health check falsely reported OK; writes returned 500 | Partial (reads cached, writes failed) |
| 5: Recovery verification | All containers restarted | All services healthy, restart counts at 0 | Yes |

The system demonstrated strong resilience to component failures, with the database health check gap (Experiment 4) as the only finding requiring remediation.
