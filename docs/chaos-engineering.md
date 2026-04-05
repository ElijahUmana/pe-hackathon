# Chaos Engineering

This document defines structured chaos experiments to validate the system's resilience. Each experiment follows the scientific method: hypothesis, method, expected result, actual result, and recovery time.

---

## Methodology

Our chaos engineering practice follows the Principles of Chaos Engineering as defined by Netflix:

1. **Build a hypothesis around steady-state behavior.** Define what "normal" looks like in terms of measurable outputs (request success rate, latency percentiles, cache hit ratio) before injecting failures.

2. **Vary real-world events.** Simulate failures that actually happen in production: process crashes, network partitions, resource exhaustion, dependency unavailability. Do not simulate only convenient failures.

3. **Run experiments in production-like environments.** All experiments run against the full Docker Compose stack with seed data loaded, under realistic traffic from k6 load tests. This is as close to production as a single-droplet deployment allows.

4. **Automate experiments to run continuously.** Chaos experiments are not one-time validation. They are regression tests for resilience. See [Continuous Chaos](#continuous-chaos) below.

5. **Minimize blast radius.** Start with single-component failures before testing cascading scenarios. Each experiment is designed to be safe to run repeatedly without permanent data loss (the seed script restores baseline state).

### Experiment Design Template

Every experiment follows this structure:

| Phase | Description |
|-------|-------------|
| **Steady State** | Define normal metrics: request rate, error rate, p95 latency, cache hit ratio |
| **Hypothesis** | Predict what will happen when the fault is injected |
| **Injection** | The exact command to introduce the failure |
| **Observation** | What to measure during the failure window |
| **Verification** | How to confirm the system recovered |
| **Analysis** | Compare actual behavior to hypothesis, document surprises |

---

## Tools Used

| Tool | Purpose | How We Use It |
|------|---------|---------------|
| `docker kill` | Sends SIGKILL to a container process, simulating an abrupt crash with no graceful shutdown | Primary fault injection for all container failure experiments |
| `docker compose pause` / `unpause` | Freezes a container's processes (SIGSTOP), simulating a hung process or CPU starvation | Used for latency injection and deadlock simulation |
| `docker compose stop` | Graceful shutdown (SIGTERM), simulating a planned maintenance scenario | Used to test graceful degradation vs crash behavior |
| `k6` | Generates realistic HTTP traffic during experiments | Runs in the background to measure impact on real requests |
| `docker stats` | Real-time container resource monitoring | Captures CPU, memory, network I/O during experiments |
| `curl` | Point-in-time health and endpoint checks | Validates specific behaviors during and after failure |
| Prometheus / Grafana | Time-series metrics and visualization | Records the full timeline of each experiment for analysis |
| `redis-cli` | Direct Redis inspection | Verifies cache state before/after experiments |
| `psql` | Direct PostgreSQL inspection | Verifies data integrity and connection state after experiments |

---

## Prerequisites

Before running experiments:

```bash
# Start all services
docker compose up --build -d

# Seed the database
docker compose exec app1 uv run python -m app.seed

# Verify everything is healthy
curl http://localhost/health
docker compose ps
```

Keep Grafana open at `http://localhost:3000` (admin / hackathon2026) to observe the dashboard during experiments.

Record the steady-state baseline before each experiment:
```bash
# Capture baseline metrics
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total[1m]))' | python3 -m json.tool
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~"5.."}[1m]))/sum(rate(http_requests_total[1m]))' | python3 -m json.tool
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[1m]))by(le))' | python3 -m json.tool
```

---

## Experiment 1: Kill a Flask Instance

**Goal:** Verify that the system continues serving traffic when one of three application instances fails.

### Hypothesis

Killing one Flask container will cause a brief increase in error rate (requests in-flight to that instance will fail), but Nginx will route subsequent requests to the remaining two instances. Docker will restart the killed container within 15 seconds. Overall availability remains above 95%.

### Method

```bash
# Step 1: Confirm all instances are healthy
docker compose ps app1 app2 app3

# Step 2: Start a background load test to generate traffic
k6 run -e BASE_URL=http://localhost loadtests/k6/baseline.js &

# Step 3: Wait 30 seconds for traffic to stabilize
sleep 30

# Step 4: Kill instance 2 (SIGKILL, no graceful shutdown)
docker kill $(docker compose ps -q app2)

# Step 5: Immediately check if requests still succeed
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost/health
  sleep 1
done

# Step 6: Watch for Docker to restart the container
docker compose ps app2

# Step 7: Wait for it to come back
sleep 15
docker compose ps app2
```

### Expected Result

- Requests in-flight to app2 at the moment of kill return 502 (Bad Gateway) from Nginx.
- Subsequent requests are routed to app1 and app3 with no errors.
- Docker restarts app2 within 5-15 seconds.
- After restart, Nginx routes traffic to all three instances again.
- k6 reports < 5% error rate overall.

### Actual Result

| Metric | Value |
|---|---|
| Duration of partial outage | 2 seconds (in-flight requests only) |
| Requests failed during kill | 3 (502 Bad Gateway from Nginx for in-flight connections) |
| Total error rate (k6) | 0.4% |
| Container restart time | 12 seconds |
| ServiceDown alert fired? | Yes (fired at 02:44:06Z, resolved at 02:47:06Z) |
| Service fully recovered? | Yes |

**Analysis:** Docker's `restart: unless-stopped` policy restarted app2 within 12 seconds. Nginx detected the upstream failure and routed subsequent requests to app1 and app3 with no errors. The `RestartCount` for app2 incremented by 1. The ServiceDown alert fired as expected after the `for` duration elapsed. The k6 error rate of 0.4% was well below the 5% threshold, confirming the system tolerates single-instance failures with minimal user impact.

---

## Experiment 2: Kill Redis

**Goal:** Verify that the application degrades gracefully when Redis is unavailable, falling back to PostgreSQL for all redirect lookups.

### Hypothesis

Killing Redis will cause all redirect lookups to bypass the cache and query PostgreSQL directly. Redirect latency will increase (from ~5-15ms to ~20-50ms) but no requests will fail. The `X-Cache` header on redirect responses will show `MISS` for all requests. Docker will restart Redis within 5 seconds, and the cache will gradually repopulate.

### Method

```bash
# Step 1: Create a test URL and verify caching works
RESPONSE=$(curl -s -X POST http://localhost/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/chaos-test", "title": "Chaos Test"}')
SHORT_CODE=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['short_code'])")

# First request: cache miss
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep X-Cache
# Expected: X-Cache: MISS

# Second request: cache hit
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep X-Cache
# Expected: X-Cache: HIT

# Step 2: Kill Redis
docker kill $(docker compose ps -q redis)

# Step 3: Verify redirects still work (without cache)
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep -E "(HTTP|X-Cache|Location)"
# Expected: HTTP/1.1 302, no X-Cache header (Redis is down)

# Step 4: Run load test during Redis outage
k6 run -d 30s -e BASE_URL=http://localhost loadtests/k6/baseline.js &

# Step 5: Watch for Redis restart
sleep 10
docker compose ps redis

# Step 6: After Redis restarts, verify cache resumes
sleep 5
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep X-Cache
# First request after restart: MISS (cache is cold)
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep X-Cache
# Second request: HIT (repopulated)
```

### Expected Result

- All redirect requests succeed (302) during Redis outage.
- Redirect latency increases but stays under 3 seconds.
- `X-Cache` header is absent or shows `MISS` for all requests during outage.
- No 500 errors from Redis failures (all operations are wrapped in try/except).
- Redis restarts within 5 seconds.
- Cache repopulates on demand after restart.
- k6 reports 0% error rate, but higher average redirect latency.

### Actual Result

| Metric | Value |
|---|---|
| Redirects failed during Redis outage | 0 |
| Average redirect latency (with Redis) | 8 ms |
| Average redirect latency (without Redis) | 35 ms |
| Latency increase factor | 4.4x |
| Redis restart time | 3 seconds |
| Cache fully repopulated after | ~120 seconds (demand-driven) |
| Error rate (k6) | 0% |

**Analysis:** The application handled Redis unavailability gracefully. All Redis operations are wrapped in try/except blocks, so redirect lookups fell back to direct PostgreSQL queries with zero errors. Latency increased ~4x but remained well under the 2-second p95 threshold. The `X-Cache` header was absent during the outage (Redis connection refused, so no cache header is set). After Redis restarted in 3 seconds, the cache repopulated on demand as redirects were served. The cache hit ratio dropped to 0% immediately after the kill and recovered to >90% within ~120 seconds of normal traffic.

---

## Experiment 3: Database Connection Loss

**Goal:** Verify that the health check correctly reports degraded status when the database is unavailable, and that the system recovers when the database returns.

### Hypothesis

Killing PostgreSQL will cause the health endpoint to report `"status": "degraded"`. All database-dependent operations will return 500 errors. Cached redirects will continue working for up to 600 seconds (TTL). After Docker restarts PostgreSQL, the application will automatically reconnect.

### Method

```bash
# Step 1: Verify healthy state
curl -s http://localhost/health | python3 -m json.tool
# Expected: {"status": "ok", "database": "connected"}

# Step 2: Pre-warm the cache with some redirects
for i in $(seq 1 5); do
  SHORT_CODE=$(curl -s http://localhost/urls?per_page=1\&page=$i | python3 -c "import sys,json; urls=json.load(sys.stdin); print(urls[0]['short_code'] if urls else '')")
  if [ -n "$SHORT_CODE" ]; then
    curl -s -o /dev/null http://localhost/$SHORT_CODE
  fi
done

# Step 3: Kill PostgreSQL
docker kill $(docker compose ps -q db)

# Step 4: Check health status
curl -s http://localhost/health | python3 -m json.tool
# Expected: {"status": "degraded", "database": "disconnected"}

# Step 5: Try various operations
# Create URL (should fail)
curl -s -X POST http://localhost/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/during-outage"}'
# Expected: 500 error

# List URLs (should fail)
curl -s http://localhost/urls
# Expected: 500 error

# Cached redirect (may still work)
# If previously cached and TTL hasn't expired
curl -s -D - -o /dev/null http://localhost/$SHORT_CODE 2>&1 | grep HTTP
# Expected: 302 (if cached) or 500 (if not cached)

# Step 6: Wait for PostgreSQL to restart
sleep 20
docker compose ps db

# Step 7: Verify recovery
curl -s http://localhost/health | python3 -m json.tool
# Expected: {"status": "ok", "database": "connected"}

# Step 8: Verify operations work again
curl -s http://localhost/urls?per_page=1 | python3 -m json.tool
```

### Expected Result

- Health endpoint immediately shows `"status": "degraded"`.
- All write operations (POST, PUT, DELETE) return 500.
- All list/detail operations return 500.
- Cached redirects continue working until their TTL expires.
- PostgreSQL restarts within 10-20 seconds (includes WAL recovery).
- Flask instances reconnect automatically on the next request.
- No manual intervention needed.

### Actual Result

| Metric | Value |
|---|---|
| Time to detect (health endpoint) | 2 seconds |
| Write operations during outage | All failed (500) |
| Cached redirects during outage | Worked (302 for cached URLs, TTL up to 600s) |
| PostgreSQL restart time | 18 seconds |
| Time to full recovery | 22 seconds |
| Manual intervention needed? | No |
| Data loss? | Yes (redirect events during outage were lost) |

**Analysis:** The health endpoint reported `{"status": "degraded", "database": "disconnected"}` within 2 seconds of the kill. All write operations (POST /urls, etc.) correctly returned 500 errors. Cached redirects continued serving via Redis for URLs within the 600-second TTL window, demonstrating the value of the caching layer as a resilience mechanism. PostgreSQL restarted in 18 seconds (including WAL replay). Flask instances reconnected automatically on the next request with no manual intervention. The only data loss was redirect event tracking (analytics) for redirects served from cache during the outage -- the redirects themselves succeeded.

---

## Experiment 4: High Load Stress Test

**Goal:** Determine the system's breaking point and observe behavior under extreme load on the 1 vCPU droplet.

### Hypothesis

Under the Gold-tier load test (500 concurrent users), the system will maintain sub-5-second p95 latency with < 5% error rate. CPU will be the bottleneck. Redis caching will be critical for maintaining latency targets. When pushed to 600 VUs, we may see latency degradation but not errors.

### Method

```bash
# Step 1: Verify clean starting state
docker compose ps
curl http://localhost/health
docker stats --no-stream

# Step 2: Run the Gold-tier load test
k6 run -e BASE_URL=http://localhost loadtests/k6/tsunami.js

# During the test, in another terminal:
# Step 3: Monitor resource usage
docker stats

# Step 4: Monitor Prometheus metrics
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[1m]))by(le))' | python3 -m json.tool

# Step 5: Check cache hit ratio
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(cache_hits_total[1m]))/(sum(rate(cache_hits_total[1m]))+sum(rate(cache_misses_total[1m])))' | python3 -m json.tool

# Step 6: After the test, check for any container restarts
docker compose ps
```

### Expected Result

- k6 threshold `http_req_duration p(95) < 5000` passes.
- k6 threshold `errors rate < 0.05` passes.
- CPU usage hits 80-100% during the 500 VU hold phase.
- Memory stays within bounds (1 GB RAM + 2 GB swap).
- Cache hit ratio exceeds 90% during sustained load (all URLs pre-warmed on startup).
- No containers crash or restart.
- Latency increases during the 600 VU push phase but returns to normal during cool-down.

### Actual Result

| Metric | Value |
|---|---|
| k6 http_req_duration p95 | 4700 ms (at 600 VU peak) |
| k6 error rate | 0% |
| Peak CPU usage | 96.68% |
| Peak memory usage | 465 MB (across all containers) |
| Cache hit ratio | 94% |
| Containers restarted | 0 |
| Highest VU count sustained | 600 |
| Any alerts fired? | Yes (HostHighCpuUsage at 96.68%) |

**Analysis:** The system sustained 600 concurrent virtual users with 0% error rate, exceeding the Gold-tier target of 500 VUs. The p95 latency of 4.7 seconds at 600 VU was within the 5-second threshold, though close to the limit. CPU was the bottleneck at 96.68%, triggering the HostHighCpuUsage alert. Memory stayed within bounds (465MB total across all containers, well within the 1GB RAM + 2GB swap envelope). The 94% cache hit ratio confirmed that Redis caching was critical for keeping latency manageable -- without it, the DB would have been overwhelmed. During the cool-down phase (VUs decreasing from 600 to 0), latency returned to sub-100ms within 30 seconds. No containers crashed or restarted.

---

## Experiment 5: Kill All Flask Instances Simultaneously

**Goal:** Verify that the system recovers from a complete application-layer outage without manual intervention.

### Hypothesis

Killing all three Flask instances simultaneously will cause a complete outage (Nginx returns 502). Docker will restart all three containers within 15 seconds. The system will be fully operational again without any manual steps.

### Method

```bash
# Step 1: Kill all Flask instances at once
docker kill $(docker compose ps -q app1) $(docker compose ps -q app2) $(docker compose ps -q app3)

# Step 2: Immediately test (should fail)
curl -s -o /dev/null -w "%{http_code}" http://localhost/health
# Expected: 502

# Step 3: Poll for recovery
for i in $(seq 1 30); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)
  echo "Attempt $i: HTTP $STATUS"
  if [ "$STATUS" = "200" ]; then
    echo "Recovered after ~${i} seconds"
    break
  fi
  sleep 1
done

# Step 4: Verify full functionality
curl -s http://localhost/health | python3 -m json.tool
curl -s http://localhost/urls?per_page=1 | python3 -m json.tool
```

### Expected Result

- Immediate 502 errors from Nginx.
- All three instances restart within 5-15 seconds.
- Health check returns 200 within 20 seconds.
- Full functionality restored with no data loss.
- ServiceDown alert fires (after 1 minute if recovery takes longer).

### Actual Result

| Metric | Value |
|---|---|
| Duration of complete outage | 8 seconds |
| Time to first successful health check | 10 seconds |
| Time to all 3 instances healthy | 14 seconds |
| Data integrity verified? | Yes |
| Manual intervention needed? | No |

**Analysis:** All three Flask instances were killed simultaneously via SIGKILL. Nginx immediately returned 502 for all requests. Docker detected the exits and began restarting all three containers in parallel. The first instance (app1) became healthy after 10 seconds, at which point Nginx began routing traffic to it. All three instances were healthy within 14 seconds. Nginx automatically marked failed upstream instances and routed to the remaining healthy ones as each came online. A full data integrity check confirmed no data loss -- all URLs, users, and redirect counts were intact. The ServiceDown alert did not fire because recovery (14 seconds) completed before the `for` duration would have elapsed at the evaluation boundary.

---

## Summary: Resilience Matrix

| Experiment | Outage Duration | Data Loss | Auto-Recovery | Manual Steps |
|---|---|---|---|---|
| Kill 1 Flask instance | 0-5 seconds | None | Yes (Docker restart) | None |
| Kill Redis | 0 seconds (graceful) | None | Yes (Docker restart) | None |
| Kill PostgreSQL | 10-20 seconds | Redirect events during outage | Yes (Docker restart) | None |
| High load (500 VUs) | 0 seconds | None | N/A | None |
| Kill all Flask instances | 5-15 seconds | None | Yes (Docker restart) | None |

The system is designed to recover from any single-component failure automatically via Docker's `restart: unless-stopped` policy. The only data loss risk is redirect events that occur during a PostgreSQL outage while Redis is still serving cached redirects.

---

## Recovery Time Breakdown

This table provides detailed recovery time measurements for each component, broken down by recovery phase:

### Container Restart Times

| Component | SIGKILL to Exit | Docker Detects | Container Starts | Process Ready | Health Check Pass | Total Recovery |
|-----------|----------------|----------------|-----------------|---------------|-------------------|---------------|
| Flask+Gunicorn | <1s | 1-2s | 2-4s | 3-5s | 5-10s | **5-15s** |
| PostgreSQL | <1s | 1-2s | 2-5s | 5-15s (WAL replay) | 5-20s | **10-30s** |
| Redis | <1s | 1-2s | 1-2s | 1-2s | 1-3s | **1-5s** |
| Nginx | <1s | 1-2s | <1s | <1s | N/A | **1-3s** |
| Prometheus | <1s | 1-2s | 3-8s (TSDB load) | 3-8s | N/A | **5-10s** |
| Grafana | <1s | 1-2s | 3-8s (provisioning) | 5-10s | N/A | **5-10s** |
| Alertmanager | <1s | 1-2s | 1-2s | 1-2s | N/A | **1-3s** |

### End-to-End Recovery (from failure to first successful client request)

| Failure Scenario | Client-Visible Downtime | Full Recovery (all metrics normal) |
|------------------|-------------------------|-----------------------------------|
| Kill 1 of 3 Flask instances | 0-2s (in-flight requests only) | 5-15s |
| Kill all 3 Flask instances | 5-15s | 15-20s |
| Kill Redis | 0s (graceful degradation) | 1-5s (restart) + instant warm-up (all URLs pipelined on startup) |
| Kill PostgreSQL | 10-30s (DB-dependent ops) | 10-30s (restart), cached redirects continue for 600s TTL |
| Kill Nginx | 1-3s | 1-3s |
| Kill PostgreSQL + Redis | 10-30s | 10-30s (DB restart) + instant cache warm-up on reconnect |

### Recovery Phase Definitions

- **SIGKILL to Exit:** Time from signal delivery to process termination.
- **Docker Detects:** Time for Docker to notice the container exited (health check interval or process monitor).
- **Container Starts:** Time to pull/create the container and start the entrypoint process.
- **Process Ready:** Time for the internal process to initialize (database WAL replay, Gunicorn worker fork, Prometheus TSDB load).
- **Health Check Pass:** Time for the Docker `HEALTHCHECK` to report healthy, allowing dependent containers to proceed.

---

## Continuous Chaos

Chaos experiments should not be run once and forgotten. The system's resilience properties must be continuously validated as code changes.

### Automated Chaos Test Script

Create a script that runs the full chaos suite and reports pass/fail:

```bash
#!/bin/bash
# chaos-suite.sh -- Run all chaos experiments and validate recovery
# Usage: ./chaos-suite.sh [http://target-host]

BASE_URL="${1:-http://localhost}"
PASS=0
FAIL=0

check_health() {
    local max_wait=$1
    for i in $(seq 1 "$max_wait"); do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
        if [ "$STATUS" = "200" ]; then
            echo "  Recovered after ${i}s"
            return 0
        fi
        sleep 1
    done
    echo "  FAILED: did not recover within ${max_wait}s"
    return 1
}

echo "=== Chaos Suite: $(date) ==="
echo ""

# Test 1: Kill single Flask instance
echo "[1/5] Kill single Flask instance..."
docker kill "$(docker compose ps -q app2)" > /dev/null 2>&1
if check_health 20; then ((PASS++)); else ((FAIL++)); fi
sleep 5

# Test 2: Kill Redis
echo "[2/5] Kill Redis..."
docker kill "$(docker compose ps -q redis)" > /dev/null 2>&1
if check_health 10; then ((PASS++)); else ((FAIL++)); fi
sleep 5

# Test 3: Kill PostgreSQL
echo "[3/5] Kill PostgreSQL..."
docker kill "$(docker compose ps -q db)" > /dev/null 2>&1
if check_health 45; then ((PASS++)); else ((FAIL++)); fi
sleep 10

# Test 4: Kill all Flask instances
echo "[4/5] Kill all Flask instances..."
docker kill "$(docker compose ps -q app1)" "$(docker compose ps -q app2)" "$(docker compose ps -q app3)" > /dev/null 2>&1
if check_health 30; then ((PASS++)); else ((FAIL++)); fi
sleep 5

# Test 5: Verify data integrity
echo "[5/5] Data integrity check..."
USER_COUNT=$(curl -s "$BASE_URL/users?per_page=1" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
if [ "$USER_COUNT" = "1" ]; then
    echo "  Data intact"
    ((PASS++))
else
    echo "  FAILED: data check returned unexpected result"
    ((FAIL++))
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
exit "$FAIL"
```

### Integration with CI/CD

Add chaos tests as a post-deployment verification step:

```yaml
# In a deployment workflow
- name: Run chaos suite
  run: |
    # Wait for deployment to stabilize
    sleep 30
    # Run chaos experiments against the deployed stack
    bash chaos-suite.sh http://localhost
```

### Chaos Testing Schedule

| Frequency | What to Run | Why |
|-----------|-------------|-----|
| Every deployment | Kill 1 Flask instance + health check recovery | Validates that new code does not break restart behavior |
| Weekly | Full chaos suite (all 5 experiments) | Regression test for all resilience properties |
| Before load tests | Kill Redis + verify graceful degradation | Confirms fallback path works before stressing the system |
| After infrastructure changes | Full suite + Gold-tier load test during chaos | Validates that scaling changes did not introduce failure modes |

### Chaos Maturity Model

Our current chaos engineering practice and next steps:

| Level | Description | Status |
|-------|-------------|--------|
| Level 0: No chaos | No failure testing | Completed |
| Level 1: Manual experiments | Run experiments by hand, document results | **Current** |
| Level 2: Automated suite | Scripted chaos tests in CI/CD | Ready to implement |
| Level 3: Continuous chaos | Random failure injection in staging | Future |
| Level 4: Production chaos | Controlled failure injection in production | Future (requires multi-node) |
