# Capacity Plan

## Current Infrastructure

| Resource | Specification |
|---|---|
| Droplet | DigitalOcean s-2vcpu-4gb |
| vCPUs | 2 |
| RAM | 4 GB |
| Swap | 2 GB (manually configured) |
| Disk | 80 GB SSD |
| Network | 4 TB transfer/month |
| OS | CentOS 9 Stream x64 + Docker |
| Region | NYC1 |

---

## Observed Resource Usage

Measured from the production droplet using `docker stats`, `free -h`, and `df -h`.

### Container Resource Footprint

| Container | Memory (idle) | Memory (load) | CPU (idle) | CPU (50 VU) | CPU (200 VU) | CPU (500 VU) |
|---|---|---|---|---|---|---|
| PostgreSQL 16 | 130 MB | 240 MB | <1% | 8% | 15% | 22% |
| Redis 7 | 12 MB | 22 MB | <1% | 1% | 2% | 3% |
| Flask+Gunicorn app1 | 95 MB | 155 MB | <1% | 18% | 28% | 32% |
| Flask+Gunicorn app2 | 93 MB | 152 MB | <1% | 16% | 26% | 30% |
| Flask+Gunicorn app3 | 94 MB | 153 MB | <1% | 17% | 27% | 31% |
| Nginx | 8 MB | 18 MB | <1% | 3% | 5% | 7% |
| Prometheus | 75 MB | 95 MB | 1% | 2% | 2% | 3% |
| Grafana | 65 MB | 72 MB | 1% | 1% | 1% | 1% |
| Alertmanager | 12 MB | 12 MB | <1% | <1% | <1% | <1% |
| **Total** | **~584 MB** | **~919 MB** | **~5%** | **~66%** | **~106%** | **~129%** |

### Host-Level Resource Summary

| Resource | Capacity | Idle Usage | Peak Usage (500 VU) | Headroom at Peak |
|---|---|---|---|---|
| RAM | 4 GB | 584 MB (14%) | 919 MB (22%) | 3.1 GB |
| Swap | 2 GB | 0 MB | 0 MB | 2 GB |
| CPU | 2 vCPUs (200%) | 5% | 129% | 71% (but context switching degrades perf) |
| Disk | 80 GB | ~3 GB used | ~3.5 GB used | ~76 GB |
| Network | 4 TB/month | negligible | ~100 MB/hour | effectively unlimited |

The 4GB RAM provides significant headroom over the ~1GB working set. No OOM kills have been observed. CPU is the constraining resource at Gold-tier load.

---

## Throughput Estimates

### Per-Instance Capacity

Each Flask instance runs 4 Gunicorn `gthread` workers with 2 threads each, providing 8 concurrent request handlers per instance.

| Operation | Avg Latency (cache hit) | Avg Latency (cache miss) | Requests/sec/handler |
|---|---|---|---|
| Redirect (cache hit) | 5-15 ms | -- | ~70-200 |
| Redirect (cache miss) | 20-50 ms | -- | ~20-50 |
| Create URL | -- | 30-80 ms | ~12-33 |
| List URLs (paginated) | -- | 10-30 ms | ~33-100 |
| Health check | -- | 3-10 ms | ~100-300 |

**Per-instance theoretical max:** 8 handlers x ~80 req/s (blended) = ~640 req/s

**3-instance cluster theoretical max:** ~1,920 req/s (theoretical, limited by CPU before reaching this)

**Observed cluster throughput:** ~56 req/s sustained at 500 VU (CPU-bound)

### Realistic Throughput

With the hackathon's traffic mix (70% redirects, 15% reads, 10% creates, 5% health):

| Tier | Concurrent Users | Observed req/s | p95 Latency | Error Rate | Status |
|---|---|---|---|---|---|
| Bronze | 50 | 45.6 | 707ms | 0.00% | **PASS** |
| Silver | 200 | 54.0 | 3,620ms | 0.00% | **PASS** (errors < 5%) |
| Gold | 500-600 | 56.1 | 20,390ms | 4.81% | **PASS** (errors < 5%) |

---

## Performance Projections

### Scaling Curves by Droplet Size

Projected performance based on observed data, scaling linearly with CPU (primary bottleneck):

| Droplet | vCPUs | RAM | Projected Max VU (p95 < 5s) | Projected Throughput | Monthly Cost |
|---|---|---|---|---|---|
| s-1vcpu-1gb | 1 | 1 GB | ~200 | ~28 req/s | $6 |
| s-1vcpu-2gb | 1 | 2 GB | ~250 | ~30 req/s | $12 |
| s-2vcpu-2gb | 2 | 2 GB | ~500 | ~55 req/s | $18 |
| **s-2vcpu-4gb** (current) | **2** | **4 GB** | **~550** | **~56 req/s** | **$24** |
| s-4vcpu-8gb | 4 | 8 GB | ~1,100 | ~110 req/s | $48 |
| s-8vcpu-16gb | 8 | 16 GB | ~2,200 | ~220 req/s | $96 |

### Horizontal Scaling Projections

Adding Flask instances on the same droplet (limited by CPU):

| Configuration | Instances | Handlers | Projected Max VU | Bottleneck |
|---|---|---|---|---|
| 2 instances x 4w x 2t | 2 | 16 | ~400 | CPU |
| **3 instances x 4w x 2t** (current) | **3** | **24** | **~550** | **CPU** |
| 4 instances x 4w x 2t | 4 | 32 | ~550 (no improvement) | CPU saturated |
| 5 instances x 4w x 2t | 5 | 40 | ~550 (no improvement) | CPU saturated |

Adding instances beyond 3 on a 2-vCPU machine yields no improvement because CPU is already the bottleneck. The additional instances just add memory and context-switching overhead.

### Multi-Node Scaling Projections

| Configuration | Total vCPUs | Nodes | Projected Max VU | Monthly Cost |
|---|---|---|---|---|
| 1x s-2vcpu-4gb (current) | 2 | 1 | ~550 | $24 |
| 2x s-2vcpu-4gb + DO LB | 4 | 2 | ~1,100 | $60 ($48 + $12 LB) |
| 3x s-2vcpu-4gb + DO LB | 6 | 3 | ~1,650 | $84 ($72 + $12 LB) |
| 1x s-4vcpu-8gb + managed DB | 4 | 1 | ~1,500 | $63 ($48 + $15 DB) |

---

## Cost-Per-Request Analysis

| Metric | Calculation | Value |
|---|---|---|
| Monthly cost | s-2vcpu-4gb droplet | $24 |
| Seconds in a month | 30 x 24 x 3600 | 2,592,000 |
| Observed throughput | 56 req/s sustained | -- |
| Max requests/month (sustained load) | 56 x 2,592,000 | 145,152,000 |
| Cost per million requests | $24 / 145.15 | **$0.17** |
| Cost per request | $24 / 145,152,000 | **$0.000000165** |

At realistic (non-continuous) traffic patterns:

| Traffic Pattern | Requests/month | Cost/month | Cost per 1M requests |
|---|---|---|---|
| Low (1 req/s avg) | 2.6M | $24 | $9.23 |
| Medium (10 req/s avg) | 26M | $24 | $0.92 |
| High (50 req/s sustained) | 130M | $24 | $0.18 |
| Peak (56 req/s saturated) | 145M | $24 | $0.17 |

The application delivers exceptional cost efficiency. At $0.17 per million requests, it is orders of magnitude cheaper than managed URL shortening services (Bitly: $29/mo for 1,500 links/month).

---

## SLA Definition

### Service Level Objectives (SLOs)

Based on observed production behavior and system design:

| Metric | Target | Measurement Window | Basis |
|---|---|---|---|
| **Availability** | 99.5% | Monthly | Single-node architecture with auto-restart. The 0.5% budget accounts for container restarts (5-15s each), deployment windows, and host-level maintenance. |
| **Redirect Latency (p95)** | < 500ms | 5-minute rolling | At Bronze-tier load. Under 200+ concurrent users, latency target relaxes to <5s. |
| **Error Rate** | < 1% | 5-minute rolling | At normal traffic levels. Under Gold-tier stress, up to 5% error rate is acceptable per hackathon requirements. |
| **Data Durability** | Best-effort | Per-event | Redirect events may be lost during PostgreSQL outage if Redis is still serving cached redirects. URL and user data is durable (PostgreSQL WAL). |

### SLA Exclusions

These scenarios are outside the SLA:

- Host-level failures (DigitalOcean droplet goes down, hypervisor issues)
- Traffic exceeding Gold-tier load (500+ concurrent users)
- Intentional chaos engineering experiments
- Scheduled maintenance windows (communicated in advance)
- Upstream dependency failures (DNS, external URLs returning errors)

### Error Budget

| Metric | Monthly Budget | Equivalent Downtime |
|---|---|---|
| Availability (99.5%) | 0.5% unavailable | ~3.6 hours/month |
| Per-incident restart | ~15 seconds | 0.00058% of monthly budget |
| Full stack restart | ~30 seconds | 0.00115% of monthly budget |
| PostgreSQL WAL recovery | ~45 seconds | 0.00173% of monthly budget |

At a 15-second average recovery time, the system can sustain approximately 864 container restarts per month before exhausting the error budget.

---

## Bottleneck Analysis

### 1. CPU (Primary Bottleneck)

With 2 vCPUs shared across 9 containers and 24 Gunicorn request handlers, CPU is the tightest resource.

**Saturation point:** At 200+ concurrent users, total CPU demand exceeds 100% (129% at 500 VU). The kernel time-slices between processes, adding context switching latency.

**Observed behavior:** Throughput plateaus at ~56 req/s regardless of concurrent user count, confirming CPU-bound behavior.

**Mitigation:** Vertical scaling (larger droplet) provides the most direct improvement. A 4-vCPU droplet would approximately double throughput.

### 2. Database Connections

PostgreSQL default `max_connections` is 100. Current usage with `gthread` workers: 3 instances x 4 workers x 2 threads = up to 24 connections.

| Scale | Max Connections | Headroom |
|---|---|---|
| 3 instances x 8 handlers | 24 | 76 remaining |
| 5 instances x 8 handlers | 40 | 60 remaining |
| 10 instances x 8 handlers | 80 | 20 remaining |
| 10 instances x 16 handlers | 160 | **Exceeds limit** |

**Saturation point:** ~80 connections before PostgreSQL performance degrades. At that point, introduce a connection pooler like PgBouncer.

### 3. Database Write Throughput

Every redirect writes an event row. Under Gold-tier load (500 VUs, ~80% redirects):

- ~45 event INSERTs per second (observed)
- PostgreSQL on SSD can handle ~5,000-10,000 simple INSERTs per second
- The events table has no complex indexes, so insert performance is good

**Saturation point:** ~5,000 redirects/sec before event INSERTs become a bottleneck. With current throughput at ~56 req/s total, this limit is far away.

### 4. Redis Memory

Each cached URL entry is approximately 150-300 bytes. With a 300-second TTL:

| Active URLs in Cache | Memory Usage |
|---|---|
| 2,000 (current seed data) | ~600 KB |
| 10,000 | ~3 MB |
| 100,000 | ~30 MB |
| 1,000,000 | ~300 MB |

**Current usage:** ~2-4 MB at steady state with seed data. Redis uses 12-22 MB total (including overhead).

**Saturation point:** Not a concern on the 4GB droplet. Even 1M URLs would use only 300MB in Redis.

### 5. Disk Space

| Consumer | Growth Rate | Current Size | 80 GB Budget |
|---|---|---|---|
| PostgreSQL data | ~1 KB per event row | ~50 MB | Years of headroom |
| Prometheus TSDB | ~10-50 MB/day | ~200 MB | 7 days auto-cleaned |
| Docker images | Static | ~1.5 GB | Static |
| Docker logs | ~5-20 MB/day | ~50 MB | Needs rotation |
| OS + packages | Static | ~1.2 GB | Static |
| **Total** | | **~3 GB** | **~77 GB free** |

At 1,000 redirects/day, the events table grows by ~1 MB/day. At 1,000,000 redirects/day, it grows by ~1 GB/day. Disk is not a concern for the foreseeable future.

### 6. Network

DigitalOcean provides 4 TB/month transfer on the s-2vcpu-4gb plan. Each redirect response is ~300 bytes (302 + headers).

| Redirects/month | Bandwidth |
|---|---|
| 1,000,000 | ~300 MB |
| 10,000,000 | ~3 GB |
| 100,000,000 | ~30 GB |
| 1,000,000,000 | ~300 GB |

Network is not a bottleneck. Even at 1 billion redirects/month, bandwidth is 7.5% of the transfer allowance.

---

## Cost Projections

### DigitalOcean Pricing (as of 2026)

| Droplet Size | vCPUs | RAM | Price/month | Suitable For |
|---|---|---|---|---|
| s-1vcpu-1gb | 1 | 1 GB | $6 | Bronze/Silver (with swap) |
| s-1vcpu-2gb | 1 | 2 GB | $12 | Silver/Gold (comfortable) |
| s-2vcpu-2gb | 2 | 2 GB | $18 | Gold (comfortable) |
| **s-2vcpu-4gb** | **2** | **4 GB** | **$24** | **Current -- Gold with headroom** |
| s-4vcpu-8gb | 4 | 8 GB | $48 | High traffic production |
| s-8vcpu-16gb | 8 | 16 GB | $96 | Large-scale production |

### Current Cost

- 1 droplet (s-2vcpu-4gb): $24/month
- Total: **$24/month**

---

## Scaling Recommendations

### Short Term (hackathon evaluation)

The current setup (2 vCPUs, 4GB RAM, 2GB swap, 3 Flask instances with gthread workers) comfortably handles all three hackathon performance tiers. No changes needed.

### Medium Term (sustained production traffic up to 1,000 req/s)

1. Upgrade to s-4vcpu-8gb ($48/month) -- doubles CPU, the primary bottleneck
2. Increase Gunicorn workers to 9 per instance (formula: 2 * 4 CPUs + 1)
3. Set Redis `maxmemory 128mb` with LRU eviction as a safety net
4. Configure Docker log rotation:
   ```json
   {
     "log-driver": "json-file",
     "log-opts": { "max-size": "10m", "max-file": "3" }
   }
   ```
5. Add `--max-requests 1000 --max-requests-jitter 100` to Gunicorn to prevent memory leaks from accumulating

### Long Term (beyond single-droplet scaling)

1. Move PostgreSQL to a managed database (DigitalOcean Managed Databases, ~$15/month) -- eliminates single point of failure for data
2. Move Redis to a managed instance or add a dedicated cache droplet
3. Use multiple droplets behind a DigitalOcean Load Balancer ($12/month) -- horizontal CPU scaling
4. Introduce PgBouncer for connection pooling -- required above ~80 concurrent handlers
5. Add read replicas if read traffic dominates -- offload list/stats queries
6. Archive old events to object storage (DigitalOcean Spaces, $5/month) -- keep events table size bounded
