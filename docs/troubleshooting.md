# Troubleshooting

## App Won't Start

### Symptom: Container exits immediately or restarts in a loop

**Check logs:**
```bash
docker compose logs app1
```

**Cause 1: Database not ready**

The app containers depend on `db` being healthy, but if PostgreSQL is slow to initialize on first run:

```
peewee.OperationalError: could not connect to server: Connection refused
```

**Fix:** Wait for PostgreSQL to be healthy, then restart the app:
```bash
docker compose restart app1 app2 app3
```

**Cause 2: Missing environment variables**

```
KeyError: 'DATABASE_HOST'
```

**Fix:** Ensure all required environment variables are set in `docker-compose.yml`. Compare with the variables listed in [environment-variables.md](environment-variables.md).

**Cause 3: Port 5432 already in use**

If you have a local PostgreSQL running and it conflicts with the Docker PostgreSQL:

```bash
# Check what's using port 5432
lsof -i :5432

# Stop local PostgreSQL
sudo systemctl stop postgresql
# or
brew services stop postgresql
```

---

### Symptom: "Table creation skipped" warning in logs

```json
{"level": "WARNING", "message": "Table creation skipped: ..."}
```

**Cause:** The database is reachable but tables could not be created (possibly due to permissions or a concurrent connection).

**Fix:** This is usually benign on subsequent startups. Tables are created on first boot. If tables are genuinely missing, run the seed script:
```bash
docker compose exec app1 uv run python -m app.seed
```

---

## High Latency

### Symptom: p95 latency exceeds 3 seconds, HighLatency alert fires

**Check 1: Is Redis running?**
```bash
docker compose exec redis redis-cli ping
# Should return: PONG
```

If Redis is down, every redirect hits PostgreSQL directly. This dramatically increases redirect latency.

**Fix:**
```bash
docker compose restart redis
```

**Check 2: Database query performance**
```bash
docker compose exec db psql -U postgres -d hackathon_db -c "
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;"
```

If the `pg_stat_statements` extension is not available, check active queries:
```bash
docker compose exec db psql -U postgres -d hackathon_db -c "
SELECT pid, state, query, now() - query_start AS duration
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;"
```

**Check 3: Connection pool exhaustion**

Each Gunicorn worker opens its own database connection. With 3 instances x 4 workers = 12 concurrent connections. PostgreSQL's default `max_connections` is 100, so this is fine. But if you scale up significantly:

```bash
docker compose exec db psql -U postgres -c "SHOW max_connections;"
docker compose exec db psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
```

**Check 4: Which endpoint is slow?**

Check Grafana's latency panel or query Prometheus directly:
```bash
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket[5m]))by(le,endpoint))' | python3 -m json.tool
```

---

## Container Keeps Restarting

### Symptom: `docker compose ps` shows a container in a restart loop

```bash
docker compose ps
# Shows: restarting (1) 5 seconds ago
```

**Check the exit code:**
```bash
docker compose ps -a
docker inspect <container-id> --format='{{.State.ExitCode}}'
```

| Exit Code | Meaning | Likely Cause |
|---|---|---|
| 0 | Clean exit | Application shut itself down (rare) |
| 1 | Application error | Unhandled exception, check logs |
| 137 | OOM killed | Container exceeded memory limit |
| 139 | Segfault | Corrupt dependency or C extension issue |

**Exit code 137 (OOM):**
```bash
# Check system memory
free -h

# Check Docker memory usage
docker stats --no-stream
```

**Fix for OOM:** Add swap space or reduce Gunicorn workers. See [Out of Memory](#out-of-memory) below.

**Exit code 1 (Application error):**
```bash
docker compose logs --tail=50 <service-name>
```

Look for Python tracebacks. Common causes:
- Module import error (missing dependency)
- Database connection string misconfigured
- Port already bound

---

## Out of Memory

### Symptom: Containers killed by OOM, system becomes unresponsive

**Check current memory usage:**
```bash
free -h
docker stats --no-stream
```

**Immediate fix: Add swap**
```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**Reduce memory consumption:**

1. Reduce Gunicorn workers per instance (from 4 to 2):
   ```dockerfile
   CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", ...]
   ```

2. Reduce the number of Flask instances (from 3 to 2):
   Remove `app3` from `docker-compose.yml`, `nginx.conf`, and `prometheus.yml`.

3. Set Redis max memory:
   Add to the `redis` service in `docker-compose.yml`:
   ```yaml
   command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru
   ```

**Memory budget for a 1GB droplet + 2GB swap:**

| Component | Typical Memory |
|---|---|
| PostgreSQL | 100-200 MB |
| Redis | 10-50 MB |
| Flask+Gunicorn (per instance) | 80-150 MB |
| Flask x3 total | 240-450 MB |
| Prometheus | 50-100 MB |
| Grafana | 50-100 MB |
| Nginx | 5-15 MB |
| Alertmanager | 10-20 MB |
| OS overhead | 100-150 MB |
| **Total** | **~565-1085 MB** |

---

## Port Conflicts

### Symptom: "Bind for 0.0.0.0:80: address already in use"

**Find what's using the port:**
```bash
sudo lsof -i :80
# or
sudo ss -tlnp | grep :80
```

**Common conflicts:**

| Port | Our Service | Possible Conflict |
|---|---|---|
| 80 | Nginx | Apache, another Nginx, Caddy |
| 3000 | Grafana | Node.js dev server |
| 5432 | PostgreSQL | Local PostgreSQL |
| 6379 | Redis | Local Redis |
| 9090 | Prometheus | -- |
| 9093 | Alertmanager | -- |

**Fix option 1: Stop the conflicting service**
```bash
sudo systemctl stop apache2
sudo systemctl stop nginx
```

**Fix option 2: Change the port mapping in docker-compose.yml**
```yaml
nginx:
  ports:
    - "8080:80"  # Use port 8080 instead of 80
```

---

## Database Issues

### Symptom: "relation does not exist" errors

```
peewee.ProgrammingError: relation "urls" does not exist
```

**Cause:** Tables were not created or the seed script was not run.

**Fix:**
```bash
docker compose exec app1 uv run python -m app.seed
```

---

### Symptom: Seed script fails with "UNIQUE constraint" errors

```
peewee.IntegrityError: duplicate key value violates unique constraint
```

**Cause:** Trying to seed into a database that already has data.

**Fix:** The seed script drops and recreates tables. If it still fails, the database might have leftover sequences:

```bash
docker compose exec db psql -U postgres -d hackathon_db -c "DROP TABLE IF EXISTS events, urls, users CASCADE;"
docker compose exec app1 uv run python -m app.seed
```

---

### Symptom: "could not connect to server" from application

```
peewee.OperationalError: could not connect to server: Connection refused
Is the server running on host "db" (172.18.0.2) and accepting
TCP/IP connections on port 5432?
```

**Cause:** PostgreSQL container is not running or not healthy.

**Fix:**
```bash
docker compose ps db
docker compose restart db
# Wait for health check to pass
docker compose ps db
# Then restart apps
docker compose restart app1 app2 app3
```

---

## Redis Issues

### Symptom: All redirects show X-Cache: MISS

**Check 1: Is Redis running?**
```bash
docker compose exec redis redis-cli ping
```

**Check 2: Is REDIS_URL correct in app environment?**
```bash
docker compose exec app1 env | grep REDIS
# Should show: REDIS_URL=redis://redis:6379/0
```

**Check 3: Can the app reach Redis?**
```bash
docker compose exec app1 python -c "
import redis
r = redis.from_url('redis://redis:6379/0')
print(r.ping())
"
```

**Fix:** If Redis is running but apps can't connect, restart everything:
```bash
docker compose restart redis app1 app2 app3
```

---

## Monitoring Issues

### Symptom: Prometheus shows targets as DOWN

Open `http://<host>:9090/targets` and check target status.

**Cause 1:** App containers are not running.
```bash
docker compose ps app1 app2 app3
```

**Cause 2:** Prometheus can't resolve container hostnames. This happens if Prometheus started before the app containers.
```bash
docker compose restart prometheus
```

**Cause 3:** The `/metrics` endpoint is returning errors.
```bash
curl http://localhost:5000/metrics
```

---

### Symptom: Grafana shows "No data"

**Check 1:** Is the Prometheus datasource configured?

Go to Grafana > Settings > Data Sources. The Prometheus datasource should point to `http://prometheus:9090`.

**Check 2:** Is Prometheus collecting data?

Go to `http://<host>:9090/graph` and query `up`. You should see data points for each Flask instance.

**Check 3:** Is the dashboard provisioned?

The dashboard is auto-provisioned from `grafana/dashboards/url-shortener.json`. If it's missing:
```bash
docker compose restart grafana
```

---

## CI Pipeline Failures

### Symptom: GitHub Actions lint step fails

```
ruff check found issues
```

**Fix locally:**
```bash
uv run ruff check .          # See all issues
uv run ruff check . --fix    # Auto-fix what's possible
```

### Symptom: Tests fail in CI but pass locally

The CI uses a real PostgreSQL database (not SQLite). Check if the test relies on SQLite-specific behavior. The test fixtures in `tests/conftest.py` use in-memory SQLite.
