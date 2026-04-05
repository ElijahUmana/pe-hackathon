# Snip -- Production-Grade URL Shortener

**Tagline:** Built to survive production. 29/29 evaluator tests. 0% errors at 500 concurrent users.

**Live:** http://64.23.250.234

**GitHub:** https://github.com/elijahumana/pe-hackathon

---

## Inspiration

Most hackathon projects prove a concept works. We wanted to prove ours works *under pressure*. The MLH Production Engineering Hackathon is about building software that survives real-world conditions -- connection storms, container crashes, traffic spikes -- not just software that runs on localhost. We treated this like a real production deployment: load-balanced, monitored, tested, and hardened.

## What it does

Snip is a URL shortener with full CRUD operations, redirect tracking with analytics, and user management. Every redirect is logged as an event, giving you a full audit trail of how your links are used.

But the URL shortener is the surface. Underneath, it is a production system:

- 3 load-balanced Flask instances behind Nginx handle requests
- PostgreSQL stores the data, Redis caches the hot path
- Prometheus scrapes metrics from every instance, Grafana visualizes them in real time
- Alertmanager fires alerts when things go wrong, a webhook receiver logs them and forwards to Discord
- Containers auto-recover from crashes in under 15 seconds
- The whole stack runs on a $24/month DigitalOcean droplet

## How we built it

**Application layer:** Flask 3.1 with Gunicorn (gthread workers, 3 workers x 4 threads per instance), Peewee ORM for database models, structured JSON logging.

**Data layer:** PostgreSQL 16 (tuned: 512MB shared_buffers, 200 max_connections) as the primary store. Redis 7 as a caching layer with 300-second TTL for redirect lookups -- this cuts database load by 75% on the hot path.

**Infrastructure:** Docker Compose orchestrating 11 containers. Nginx with least-connection load balancing across 3 app instances. Health checks on every critical service. `unless-stopped` restart policies for automatic recovery.

**Observability:** Prometheus scrapes all 3 Flask instances plus a node-exporter for host metrics. Grafana has a pre-built dashboard showing request rate, error rate, latency percentiles, cache hit ratio, and instance health. Alertmanager routes alerts (ServiceDown, HighErrorRate, HighLatency, HighMemoryUsage) to a custom webhook receiver that logs locally and forwards to Discord.

**Testing:** pytest with 149 tests at 91% code coverage. CI runs lint (ruff) and tests on every push via GitHub Actions. Load testing with k6 across three tiers: Bronze (50 users), Silver (200 users), Gold (500+ users).

**Deployment:** DigitalOcean s-2vcpu-4gb droplet. SSH deploy, docker compose up, seed data load, smoke test. Total deploy time under 2 minutes.

## Challenges we ran into

**Connection pooling under load.** At 200 concurrent users, our initial single-instance sync-worker setup hit p95 latency of 12 seconds. Each request opened a new database connection, and PostgreSQL choked. The fix was threefold: switch to gthread workers (halving memory per handler), add Redis caching (eliminating 75% of database queries on redirects), and scale to 3 instances behind Nginx. Final result: p95 dropped from 12s to 1.15s at 200 users.

**Grafana datasource UID mismatch.** Grafana provisioning assigns UIDs to datasources, but the dashboard JSON referenced a hardcoded UID that did not match the provisioned one. Every panel showed "No data." We had to align the provisioned datasource UID with the one embedded in the dashboard JSON -- a single-character mismatch that cost an hour of debugging.

**Discord webhook forwarding from Docker containers.** Alertmanager inside Docker could not directly call Discord webhooks (DNS resolution, TLS verification). We built a separate webhook receiver container that Alertmanager routes to via the Docker network, and the receiver handles the external HTTPS call to Discord.

**PostgreSQL sequence reset after seed data import.** After importing seed CSVs with explicit IDs, PostgreSQL's auto-increment sequences were still at 1. Every POST to create a new user or URL failed with a duplicate key error. The fix: reset sequences to MAX(id)+1 after every seed import.

## Accomplishments we are proud of

- **29/29 evaluator tests passed**, including hidden bonus tests we did not know existed until they ran
- **149 internal tests** at **91% code coverage** -- covering edge cases, cache behavior, error handling, graceful degradation when Redis is down
- **0% error rate at 500 concurrent users** with 232 req/s throughput on a $24/month server
- **p95 latency of 807ms at 200 users** -- 3.7x under the 3-second threshold
- **Full alert pipeline in production:** Prometheus evaluates rules, Alertmanager routes alerts, webhook receiver logs and forwards to Discord. We have proof of real alerts firing and resolving during chaos experiments.
- **Chaos engineering with evidence:** Killed containers during live traffic, watched alerts fire on Discord, confirmed auto-recovery in under 15 seconds, verified zero data loss
- **6,000+ lines of documentation** across 13 docs covering architecture, API reference, deployment runbook, capacity planning, failure mode analysis, chaos engineering playbook, incident diagnosis, and bottleneck analysis

## What we learned

**Connection pooling matters more than adding instances.** Our biggest performance gain was not from scaling horizontally (which gave 2.7x throughput) but from switching to threaded workers and adding Redis caching (which gave 7.4x latency reduction at Gold tier). Throwing more servers at a problem without fixing the bottleneck just distributes the same bottleneck.

**Database indexes on hot paths are critical.** Redirect lookups by short_code went from table scans to index lookups, cutting cache-miss latency from 450ms to 35ms at p50. One index, 13x faster.

**Chaos engineering proves recovery works -- testing alone does not.** Unit tests verify code logic. Load tests verify performance. But only killing containers during live traffic proves that the restart policies, health checks, and load balancer failover actually work together. We caught a real issue: Nginx continued sending requests to a dead upstream for ~5 seconds before health checks removed it.

## What's next

- **Kubernetes migration** -- replace Docker Compose with Helm charts for proper auto-scaling and rolling deployments
- **Read replicas** -- offload list and stats queries to PostgreSQL replicas, keeping writes on the primary
- **CDN integration** -- cache redirect responses at the edge for sub-10ms global latency
- **PgBouncer** -- connection pooling proxy to push the concurrency ceiling past 1,000 users on the same hardware

## Built With

Python, Flask, PostgreSQL, Redis, Docker, Docker Compose, Nginx, Gunicorn, Prometheus, Grafana, Alertmanager, k6, GitHub Actions, DigitalOcean, Peewee, uv
