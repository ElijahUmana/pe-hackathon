# Capacity Plan

## Current Infrastructure

| Resource | Specification |
|---|---|
| Droplet | DigitalOcean s-1vcpu-1gb |
| vCPUs | 1 |
| RAM | 1 GB |
| Swap | 2 GB (manually configured) |
| Disk | 25 GB SSD |
| Network | 1 TB transfer/month |
| OS | Ubuntu + Docker |

## Container Resource Footprint

| Container | Typical Memory | CPU Usage (idle) | CPU Usage (load) |
|---|---|---|---|
| PostgreSQL 16 | 100-200 MB | <1% | 10-30% |
| Redis 7 | 10-50 MB | <1% | 1-5% |
| Flask+Gunicorn app1 | 80-150 MB | <1% | 15-25% per instance |
| Flask+Gunicorn app2 | 80-150 MB | <1% | 15-25% per instance |
| Flask+Gunicorn app3 | 80-150 MB | <1% | 15-25% per instance |
| Nginx | 5-15 MB | <1% | 2-5% |
| Prometheus | 50-100 MB | 1-2% | 2-5% |
| Grafana | 50-100 MB | 1-2% | 2-5% |
| Alertmanager | 10-20 MB | <1% | <1% |
| **Total (idle)** | **~465-935 MB** | **~5%** | |
| **Total (under load)** | **~600-1100 MB** | | **~60-100%** |

## Throughput Estimates

### Per-Instance Capacity

Each Flask instance runs 4 Gunicorn sync workers. Each worker handles one request at a time.

| Operation | Avg Latency (cache hit) | Avg Latency (cache miss) | Requests/sec/worker |
|---|---|---|---|
| Redirect (cache hit) | 5-15 ms | -- | ~70-200 |
| Redirect (cache miss) | 20-50 ms | -- | ~20-50 |
| Create URL | -- | 30-80 ms | ~12-33 |
| List URLs | -- | 10-30 ms | ~33-100 |
| Health check | -- | 5-15 ms | ~70-200 |

**Per-instance theoretical max:** 4 workers x ~100 req/s (blended) = ~400 req/s

**3-instance cluster theoretical max:** ~1,200 req/s (before database becomes the bottleneck)

### Realistic Throughput

With the hackathon's traffic mix (70% redirects, 15% reads, 10% creates, 5% health):

| Tier | Concurrent Users | Expected req/s | p95 Target | Achievable? |
|---|---|---|---|---|
| Bronze | 50 | ~100 | < 3s | Yes |
| Silver | 200 | ~400-600 | < 3s | Yes (with Redis) |
| Gold | 500 | ~1,000-2,000 | < 5s | Yes (with Redis + 3 instances) |

## Bottleneck Analysis

### 1. CPU (Primary Bottleneck)

With 1 vCPU shared across 9 containers and 12 Gunicorn workers, CPU is the tightest resource.

**Saturation point:** When the CPU is at 100% utilization, request latency increases as workers wait for CPU time. This typically occurs around 500-800 req/s depending on the operation mix.

**Mitigation:** Vertical scaling (larger droplet) or horizontal scaling (more droplets with a shared database).

### 2. Database Connections

PostgreSQL default `max_connections` is 100. Current usage: 3 instances x 4 workers = 12 connections.

| Scale | Connections | Headroom |
|---|---|---|
| 3 instances x 4 workers | 12 | 88 remaining |
| 5 instances x 4 workers | 20 | 80 remaining |
| 10 instances x 4 workers | 40 | 60 remaining |
| 10 instances x 8 workers | 80 | 20 remaining |

**Saturation point:** ~80 connections before PostgreSQL performance degrades. At that point, introduce a connection pooler like PgBouncer.

### 3. Database Write Throughput

Every redirect writes an event row. Under Gold-tier load (500 VUs, 80% redirects):

- ~800-1,600 event INSERTs per second
- PostgreSQL on SSD can handle ~5,000-10,000 simple INSERTs per second
- The events table has no complex indexes, so insert performance is good

**Saturation point:** ~5,000 redirects/sec before event INSERTs become a bottleneck.

### 4. Redis Memory

Each cached URL entry is approximately 150-300 bytes. With a 300-second TTL:

| Active URLs in Cache | Memory Usage |
|---|---|
| 1,000 | ~300 KB |
| 10,000 | ~3 MB |
| 100,000 | ~30 MB |
| 1,000,000 | ~300 MB |

**Saturation point:** With no `maxmemory` set, Redis will consume memory until the host runs out. For the 1GB droplet, set `maxmemory 64mb` with `allkeys-lru` eviction.

### 5. Disk Space

| Consumer | Growth Rate | Retention |
|---|---|---|
| PostgreSQL data | ~1 KB per event row | Unlimited |
| Prometheus TSDB | ~10-50 MB/day | 7 days (auto-cleaned) |
| Docker logs | ~5-20 MB/day | Unlimited (must configure rotation) |
| Grafana data | Minimal | Unlimited |

At 1,000 redirects/day, the events table grows by ~1 MB/day. At 1,000,000 redirects/day, it grows by ~1 GB/day.

**Mitigation:** For high-traffic deployments, partition the events table by date or archive old events.

### 6. Network

DigitalOcean provides 1 TB/month transfer. Each redirect response is ~300 bytes (302 + headers).

| Redirects/month | Bandwidth |
|---|---|
| 1,000,000 | ~300 MB |
| 10,000,000 | ~3 GB |
| 100,000,000 | ~30 GB |

Network is not a bottleneck for this application.

## Cost Projections

### DigitalOcean Pricing (as of 2026)

| Droplet Size | vCPUs | RAM | Price/month | Suitable For |
|---|---|---|---|---|
| s-1vcpu-1gb | 1 | 1 GB | $6 | Bronze/Silver (with swap) |
| s-1vcpu-2gb | 1 | 2 GB | $12 | Silver/Gold (comfortable) |
| s-2vcpu-2gb | 2 | 2 GB | $18 | Gold (comfortable) |
| s-2vcpu-4gb | 2 | 4 GB | $24 | Gold+ (headroom) |
| s-4vcpu-8gb | 4 | 8 GB | $48 | High traffic production |

### Current Cost

- 1 droplet (s-1vcpu-1gb): $6/month
- Total: **$6/month**

## Scaling Recommendations

### Short Term (hackathon evaluation)

The current setup (1 vCPU, 1GB + 2GB swap, 3 Flask instances) handles the Gold tier. No changes needed.

### Medium Term (sustained production traffic up to 1,000 req/s)

1. Upgrade to s-2vcpu-2gb ($18/month)
2. Increase Gunicorn workers to 5 per instance (formula: 2 * CPUs + 1)
3. Set Redis `maxmemory 128mb` with LRU eviction
4. Configure Docker log rotation:
   ```json
   {
     "log-driver": "json-file",
     "log-opts": { "max-size": "10m", "max-file": "3" }
   }
   ```

### Long Term (beyond single-droplet scaling)

1. Move PostgreSQL to a managed database (DigitalOcean Managed Databases, ~$15/month)
2. Move Redis to a managed instance or add a dedicated cache droplet
3. Use multiple droplets behind a DigitalOcean Load Balancer ($12/month)
4. Introduce PgBouncer for connection pooling
5. Add read replicas if read traffic dominates
6. Consider archiving old events to object storage (DigitalOcean Spaces)
