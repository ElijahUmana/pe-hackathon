# Deployment Guide

## Prerequisites

- A server with Docker and Docker Compose installed (tested on CentOS 9 Stream, Ubuntu 22.04+)
- Minimum: 2 vCPUs, 4GB RAM (recommended for all 3 hackathon performance tiers)
- Ports 80, 3000, 9090, 9093 available
- SSH access to the server
- (Optional) A domain name pointed at your server IP

## DigitalOcean Droplet Setup

### 1. Create the Droplet

```bash
# Using doctl CLI (or create via the DigitalOcean web console)
doctl compute droplet create url-shortener \
  --region nyc1 \
  --size s-2vcpu-4gb \
  --image docker-20-04 \
  --ssh-keys <your-ssh-key-fingerprint>
```

The `docker-20-04` image comes with Docker and Docker Compose pre-installed. The s-2vcpu-4gb size ($24/month) provides 2 vCPUs, 4GB RAM, and 80GB SSD -- enough to comfortably run all 9 containers and pass the Gold-tier load test.

### 2. SSH Into the Droplet

```bash
ssh root@<droplet-ip>
```

### 3. Add Swap Space

Even with 4GB RAM, swap provides a safety net for memory spikes under extreme load:

```bash
# Create 2GB swap file
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Make persistent across reboots
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Tune swappiness (prefer RAM, use swap as safety net)
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf
```

### 4. Clone the Repository

```bash
cd /opt
git clone <repo-url> url-shortener
cd url-shortener
```

### 5. Configure Environment

For Docker Compose, environment variables are set directly in `docker-compose.yml`. The defaults work for production. If you need to customize:

```bash
# Edit docker-compose.yml to change database passwords, log levels, etc.
nano docker-compose.yml
```

For Alertmanager, configure your Discord webhook:

```bash
nano alertmanager/alertmanager.yml
# Replace the webhook URL with your actual Discord webhook URL
```

## Docker Compose Deployment

### Start All Services

```bash
cd /opt/url-shortener
docker compose up --build -d
```

This starts 9 containers:
1. `db` -- PostgreSQL 16
2. `redis` -- Redis 7
3. `app1` -- Flask + Gunicorn (instance 1)
4. `app2` -- Flask + Gunicorn (instance 2)
5. `app3` -- Flask + Gunicorn (instance 3)
6. `nginx` -- Load balancer
7. `prometheus` -- Metrics collector
8. `grafana` -- Dashboard UI
9. `alertmanager` -- Alert routing

### Check Container Status

```bash
docker compose ps
```

All containers should show `Up` with health status `(healthy)` for db and redis.

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app1

# Last 100 lines
docker compose logs --tail=100 nginx
```

## Seeding the Database

After all containers are running and healthy:

```bash
docker compose exec app1 uv run python -m app.seed
```

Expected output:
```
Dropping existing tables...
Creating tables...
Loading seed data...
Loaded 400 users
Loaded 2000 URLs
Loaded 3422 events
Seed complete!
```

This drops existing tables and recreates them with the hackathon seed data. Run it only once, or any time you want to reset to the original dataset.

## Verifying the Deployment

Run these checks in order:

### 1. Health Check

```bash
curl http://localhost/health
```

Expected:
```json
{"database":"connected","status":"ok"}
```

### 2. API Endpoints

```bash
# List users
curl http://localhost/users?per_page=2

# List URLs
curl http://localhost/urls?per_page=2

# Create a URL
curl -X POST http://localhost/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "title": "Test"}'

# Redirect (should return 302)
curl -v http://localhost/<short_code_from_above>
```

### 3. Monitoring

```bash
# Prometheus targets (all should be UP)
curl http://localhost:9090/api/v1/targets | python3 -m json.tool

# Grafana (login: admin / hackathon2026)
# Open http://<droplet-ip>:3000 in a browser
```

### 4. Metrics

```bash
curl http://localhost/metrics | head -20
```

### 5. Load Test (from your local machine)

```bash
k6 run -e BASE_URL=http://<droplet-ip> loadtests/k6/baseline.js
```

## Rollback Procedure

If a deployment goes wrong, follow these steps:

### Step 1: Identify the Problem

```bash
# Check which containers are unhealthy
docker compose ps

# Check recent logs for errors
docker compose logs --tail=200 app1 app2 app3
```

### Step 2: Roll Back to Previous Version

```bash
cd /opt/url-shortener

# Check current commit
git log --oneline -5

# Roll back to the previous commit
git checkout <previous-commit-hash>

# Rebuild and restart only the app containers
docker compose up --build -d app1 app2 app3

# If infrastructure changes were involved, restart everything
docker compose up --build -d
```

### Step 3: Verify the Rollback

```bash
curl http://localhost/health
```

### Step 4: If Database Schema Changed

If the failed deployment included database schema changes:

```bash
# Re-seed to restore the original schema and data
docker compose exec app1 uv run python -m app.seed
```

This is destructive -- it drops and recreates all tables with the seed data.

### Step 5: If Nothing Works

Nuclear option -- tear down everything and start fresh:

```bash
docker compose down -v   # -v removes volumes (destroys data)
docker compose up --build -d
docker compose exec app1 uv run python -m app.seed
```

## Scaling

### Horizontal: Add More Flask Instances

To scale from 3 to 5 instances:

1. Add `app4` and `app5` to `docker-compose.yml` (copy the `app3` block, change `INSTANCE_ID`).

2. Add the new servers to `nginx/nginx.conf`:
   ```nginx
   upstream flask_app {
       least_conn;
       server app1:5000;
       server app2:5000;
       server app3:5000;
       server app4:5000;
       server app5:5000;
   }
   ```

3. Add the new targets to `prometheus/prometheus.yml`:
   ```yaml
   static_configs:
     - targets:
         - "app1:5000"
         - "app2:5000"
         - "app3:5000"
         - "app4:5000"
         - "app5:5000"
   ```

4. Rebuild and restart:
   ```bash
   docker compose up --build -d
   ```

### Vertical: Larger Droplet

Resize the DigitalOcean droplet via the console or CLI:

```bash
# Power off first
doctl compute droplet-action shutdown <droplet-id>

# Resize
doctl compute droplet-action resize <droplet-id> --size s-2vcpu-2gb

# Power on
doctl compute droplet-action power-on <droplet-id>
```

Then increase Gunicorn workers in the Dockerfile:

```dockerfile
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "8", ...]
```

The Gunicorn worker count formula: `2 * num_cpus + 1`. For 2 vCPUs, use 5 workers. For 4 vCPUs, use 9 workers.

### Scale Down

To reduce from 3 to 2 instances:

1. Remove `app3` from `docker-compose.yml`
2. Remove `app3:5000` from `nginx/nginx.conf` and `prometheus/prometheus.yml`
3. Restart:
   ```bash
   docker compose up --build -d
   docker compose rm -f app3
   ```

## Updating the Application

```bash
cd /opt/url-shortener
git pull origin main
docker compose up --build -d
```

Only the containers whose images changed will be rebuilt. PostgreSQL and Redis data persists across restarts via Docker volumes.

---

## Zero-Downtime Deployment

Docker Compose does not natively support rolling deployments, but we can approximate zero-downtime updates by restarting instances one at a time while Nginx routes around them.

### Rolling Restart Strategy

```bash
cd /opt/url-shortener

# Pull latest code
git pull origin main

# Build the new image (does not restart anything)
docker compose build

# Restart instances one at a time, waiting for each to be healthy
for instance in app1 app2 app3; do
  echo "Restarting $instance..."
  docker compose up -d --no-deps --build "$instance"

  # Wait for the instance to pass its health check
  echo "Waiting for $instance to be healthy..."
  timeout=60
  elapsed=0
  while [ $elapsed -lt $timeout ]; do
    STATUS=$(docker inspect "$(docker compose ps -q $instance)" --format='{{.State.Health.Status}}' 2>/dev/null)
    if [ "$STATUS" = "healthy" ]; then
      echo "$instance is healthy after ${elapsed}s"
      break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if [ $elapsed -ge $timeout ]; then
    echo "WARNING: $instance did not become healthy within ${timeout}s"
    echo "Rolling back..."
    git checkout HEAD~1
    docker compose up -d --no-deps --build "$instance"
    exit 1
  fi

  # Brief pause to let Nginx detect the healthy instance
  sleep 5
done

echo "All instances updated successfully."
```

**How this works:**

1. Nginx is configured with `least_conn` and will not route to a backend that refuses connections.
2. When an instance is restarting (~5-15 seconds), Nginx routes all traffic to the remaining two instances.
3. Once the instance passes its Docker `HEALTHCHECK` (polls `/health` every 30s), Nginx resumes routing to it.
4. Repeating for each instance ensures at least 2 of 3 instances are always serving traffic.

**Limitation:** There is a brief window (~5-15 seconds per instance) where capacity is reduced from 3 instances to 2. Under normal traffic, this is invisible to users. Under heavy load (Gold-tier), the temporary capacity reduction may cause a latency spike.

---

## Database Migration

The application uses Peewee's `create_tables(safe=True)` for schema management. This is a "create if not exists" approach rather than a full migration system.

### Adding a New Column

```bash
# 1. SSH into the droplet
ssh root@<droplet-ip>

# 2. Connect to the database
docker compose exec db psql -U postgres -d hackathon_db

# 3. Run the ALTER TABLE statement
ALTER TABLE urls ADD COLUMN click_count INTEGER DEFAULT 0;

# 4. Verify
\d urls

# 5. Exit psql
\q
```

### Adding a New Table

If the new table is defined in the Peewee model, it will be created automatically on the next app startup (via `create_tables(safe=True)` in the app factory). Just deploy the code:

```bash
git pull origin main
docker compose up --build -d
```

### Destructive Schema Changes

For changes that require dropping or recreating tables:

```bash
# Option 1: Re-seed (drops all tables and recreates with seed data)
docker compose exec app1 uv run python -m app.seed

# Option 2: Manual DROP + CREATE
docker compose exec db psql -U postgres -d hackathon_db -c "
  DROP TABLE IF EXISTS events, urls, users CASCADE;
"
# Then restart the apps (they will recreate tables on startup)
docker compose restart app1 app2 app3
# Then re-seed
docker compose exec app1 uv run python -m app.seed
```

### Migration Safety Checklist

Before running any schema change in production:

- [ ] Test the migration against a copy of the production schema locally
- [ ] Back up the database: `docker compose exec db pg_dump -U postgres hackathon_db > backup.sql`
- [ ] Schedule the migration during low-traffic period
- [ ] Run the migration
- [ ] Verify the schema: `\d tablename` in psql
- [ ] Verify the application: `curl http://localhost/health`
- [ ] Verify data integrity: run a few API calls that touch the changed table

---

## Monitoring Verification

After every deployment, verify that the monitoring stack is functioning correctly.

### Monitoring Verification Checklist

```bash
# 1. Verify Prometheus is scraping all targets
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
data = json.load(sys.stdin)
for group in data['data']['activeTargets']:
    print(f\"{group['labels']['instance']}: {group['health']}\")
"
# Expected: app1:5000: up, app2:5000: up, app3:5000: up

# 2. Verify metrics are being collected
curl -s 'http://localhost:9090/api/v1/query?query=up{job="flask-app"}' | python3 -m json.tool
# Expected: 3 results, all with value "1"

# 3. Verify alert rules are loaded
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys, json
data = json.load(sys.stdin)
for group in data['data']['groups']:
    for rule in group['rules']:
        print(f\"{rule['name']}: {rule['health']}\")
"
# Expected: ServiceDown: ok, HighErrorRate: ok, HighLatency: ok, HighMemoryUsage: ok

# 4. Verify Alertmanager is reachable
curl -s http://localhost:9093/api/v1/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Alertmanager status: {data['status']}\")
"

# 5. Verify Grafana is serving the dashboard
curl -s -u admin:hackathon2026 http://localhost:3000/api/search | python3 -c "
import sys, json
dashboards = json.load(sys.stdin)
for d in dashboards:
    print(f\"Dashboard: {d['title']}\")
"

# 6. Generate a test request and verify it appears in metrics
curl -s http://localhost/health > /dev/null
sleep 15  # Wait for next Prometheus scrape
curl -s 'http://localhost:9090/api/v1/query?query=http_requests_total{endpoint="health"}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
total = sum(float(r['value'][1]) for r in data['data']['result'])
print(f\"Total health check requests recorded: {total}\")
"
```

---

## Smoke Test Checklist

Run this after every deployment to verify the system is functioning end-to-end.

### Automated Smoke Test Script

```bash
#!/bin/bash
# smoke-test.sh -- Verify all critical paths after deployment
# Usage: ./smoke-test.sh [http://target-host]

BASE_URL="${1:-http://localhost}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  PASS: $name"
        ((PASS++))
    else
        echo "  FAIL: $name (expected '$expected', got '$actual')"
        ((FAIL++))
    fi
}

echo "=== Smoke Test: $(date) ==="
echo "Target: $BASE_URL"
echo ""

# 1. Health check
echo "[1/8] Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
check "GET /health returns 200" "200" "$STATUS"
DB_STATUS=$(curl -s "$BASE_URL/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database',''))" 2>/dev/null)
check "Database is connected" "connected" "$DB_STATUS"

# 2. List users
echo "[2/8] List users..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/users?per_page=1")
check "GET /users returns 200" "200" "$STATUS"

# 3. List URLs
echo "[3/8] List URLs..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/urls?per_page=1")
check "GET /urls returns 200" "200" "$STATUS"

# 4. Create a URL
echo "[4/8] Create URL..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/urls" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/smoke-test","title":"Smoke Test"}')
BODY=$(echo "$RESPONSE" | head -1)
STATUS=$(echo "$RESPONSE" | tail -1)
check "POST /urls returns 201" "201" "$STATUS"
SHORT_CODE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('short_code',''))" 2>/dev/null)

# 5. Redirect
echo "[5/8] Redirect..."
if [ -n "$SHORT_CODE" ]; then
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -L --max-redirs 0 "$BASE_URL/$SHORT_CODE" 2>/dev/null || true)
    # curl returns 000 if redirect is not followed, but -o /dev/null -w gives the actual status
    REDIR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/$SHORT_CODE")
    check "GET /$SHORT_CODE returns 302" "302" "$REDIR_STATUS"
else
    echo "  SKIP: No short code from previous step"
    ((FAIL++))
fi

# 6. Metrics endpoint
echo "[6/8] Metrics..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/metrics")
check "GET /metrics returns 200" "200" "$STATUS"

# 7. Events endpoint
echo "[7/8] Events..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/events?per_page=1")
check "GET /events returns 200" "200" "$STATUS"

# 8. Validation (should reject bad input)
echo "[8/8] Input validation..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/urls" \
  -H "Content-Type: application/json" \
  -d '{"url":"not-a-url"}')
check "POST /urls rejects invalid URL with 400" "400" "$STATUS"

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
exit "$FAIL"
```

### Manual Quick Smoke Test

If you prefer a manual check, run these commands in order and verify each output:

```bash
# Health
curl -s http://localhost/health | python3 -m json.tool

# Users exist
curl -s http://localhost/users?per_page=2 | python3 -m json.tool

# URLs exist
curl -s http://localhost/urls?per_page=2 | python3 -m json.tool

# Create + redirect
SHORT=$(curl -s -X POST http://localhost/urls \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/deploy-check"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['short_code'])")
curl -v http://localhost/$SHORT 2>&1 | grep -E "(< HTTP|< Location|< X-Cache)"

# Metrics are flowing
curl -s http://localhost/metrics | head -5
```
