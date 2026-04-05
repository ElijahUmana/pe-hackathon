# Chaos Engineering

This document defines structured chaos experiments to validate the system's resilience. Each experiment follows the scientific method: hypothesis, method, expected result, actual result, and recovery time.

Run these experiments with the full Docker Compose stack running and seed data loaded.

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

### Actual Result Template

| Metric | Value |
|---|---|
| Duration of partial outage | ___ seconds |
| Requests failed during kill | ___ |
| Total error rate (k6) | ___% |
| Container restart time | ___ seconds |
| ServiceDown alert fired? | Yes / No |
| Service fully recovered? | Yes / No |

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

### Actual Result Template

| Metric | Value |
|---|---|
| Redirects failed during Redis outage | ___ |
| Average redirect latency (with Redis) | ___ ms |
| Average redirect latency (without Redis) | ___ ms |
| Latency increase factor | ___x |
| Redis restart time | ___ seconds |
| Cache fully repopulated after | ___ seconds |
| Error rate (k6) | ___% |

---

## Experiment 3: Database Connection Loss

**Goal:** Verify that the health check correctly reports degraded status when the database is unavailable, and that the system recovers when the database returns.

### Hypothesis

Killing PostgreSQL will cause the health endpoint to report `"status": "degraded"`. All database-dependent operations will return 500 errors. Cached redirects will continue working for up to 300 seconds (TTL). After Docker restarts PostgreSQL, the application will automatically reconnect.

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

### Actual Result Template

| Metric | Value |
|---|---|
| Time to detect (health endpoint) | ___ seconds |
| Write operations during outage | All failed / Partially failed |
| Cached redirects during outage | Worked / Failed |
| PostgreSQL restart time | ___ seconds |
| Time to full recovery | ___ seconds |
| Manual intervention needed? | Yes / No |
| Data loss? | Yes (events) / No |

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
- Memory stays within bounds (1GB + 2GB swap).
- Cache hit ratio exceeds 80% during sustained load (same URLs accessed repeatedly).
- No containers crash or restart.
- Latency increases during the 600 VU push phase but returns to normal during cool-down.

### Actual Result Template

| Metric | Value |
|---|---|
| k6 http_req_duration p95 | ___ ms |
| k6 error rate | ___% |
| Peak CPU usage | ___% |
| Peak memory usage | ___ MB |
| Cache hit ratio | ___% |
| Containers restarted | ___ |
| Highest VU count sustained | ___ |
| Any alerts fired? | Yes / No |

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

### Actual Result Template

| Metric | Value |
|---|---|
| Duration of complete outage | ___ seconds |
| Time to first successful health check | ___ seconds |
| Time to all 3 instances healthy | ___ seconds |
| Data integrity verified? | Yes / No |
| Manual intervention needed? | Yes / No |

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
