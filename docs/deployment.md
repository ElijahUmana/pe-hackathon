# Deployment Guide

## Prerequisites

- A server with Docker and Docker Compose installed (tested on Ubuntu 22.04+)
- At least 1 vCPU, 1GB RAM (2GB+ swap recommended)
- Ports 80, 3000, 9090, 9093 available
- SSH access to the server
- (Optional) A domain name pointed at your server IP

## DigitalOcean Droplet Setup

### 1. Create the Droplet

```bash
# Using doctl CLI (or create via the DigitalOcean web console)
doctl compute droplet create url-shortener \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image docker-20-04 \
  --ssh-keys <your-ssh-key-fingerprint>
```

The `docker-20-04` image comes with Docker and Docker Compose pre-installed.

### 2. SSH Into the Droplet

```bash
ssh root@<droplet-ip>
```

### 3. Add Swap Space

On a 1GB droplet, swap is essential for handling load spikes:

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
