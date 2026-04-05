# MLH PE Hackathon - Evidence Index

## Live Endpoints

| Service | URL | Credentials |
|---------|-----|-------------|
| Application | http://146.190.158.231 | - |
| Health Check | http://146.190.158.231/health | - |
| Metrics (Prometheus format) | http://146.190.158.231/metrics | - |
| Grafana Dashboard | http://146.190.158.231:3000 | admin / hackathon2026 |
| Prometheus | http://146.190.158.231:9090 | - |
| Alertmanager | http://146.190.158.231:9093 | - |
| Webhook Receiver | http://146.190.158.231:9094 | - |
| GitHub Repository | https://github.com/ElijahUmana/pe-hackathon | - |
| CI/CD (GitHub Actions) | https://github.com/ElijahUmana/pe-hackathon/actions | - |

---

## Reliability Evidence

| # | File | Description |
|---|------|-------------|
| 1 | [health_endpoint.txt](health_endpoint.txt) | Health check endpoint returning JSON with database connectivity status |
| 2 | [pytest_collection.txt](pytest_collection.txt) | Full test inventory showing all 149 collected tests |
| 3 | [pytest_results.txt](pytest_results.txt) | Verbose test run output: 149 passed, 0 failed |
| 4 | [coverage_report.txt](coverage_report.txt) | Code coverage report: 91% overall coverage with per-file breakdown |
| 5 | [ci_green.txt](ci_green.txt) | GitHub Actions CI history showing 5 consecutive green builds |
| 6 | [error_handling.txt](error_handling.txt) | Clean JSON error responses for 6 different error scenarios (missing field, invalid URL, non-JSON body, 404, bad user_id, method not allowed) |
| 7 | [container_restart.txt](container_restart.txt) | Container kill + auto-restart demonstration: app2 killed, health check still passes via remaining instances, app2 auto-restarts within 30s |

## Scalability Evidence

| # | File | Description |
|---|------|-------------|
| 8 | [docker_ps.txt](docker_ps.txt) | Docker Compose showing 11 containers: 3 app instances, nginx load balancer, PostgreSQL, Redis, Prometheus, Grafana, Alertmanager, node-exporter, webhook-receiver |
| 9 | [load_test_bronze.txt](load_test_bronze.txt) | k6 load test results: 50 VUs for 1 minute, 0.00% error rate, ~90 req/s, p95 latency 27ms |
| 10 | [nginx_config.txt](nginx_config.txt) | Nginx configuration showing upstream load balancing across 3 app instances with least_conn strategy |
| 11 | [redis_cache_evidence.txt](redis_cache_evidence.txt) | Redis cache demonstration: first redirect returns X-Cache: MISS, second returns X-Cache: HIT |

## Incident Response Evidence

| # | File | Description |
|---|------|-------------|
| 12 | [json_logs.txt](json_logs.txt) | Structured JSON application logs with timestamp, logger name, level, message, HTTP method, path, status, remote_addr, user_agent |
| 13 | [metrics_endpoint.txt](metrics_endpoint.txt) | Prometheus-format metrics endpoint exposing request counts, latency histograms, cache hits/misses, active URLs |
| 14 | [prometheus_targets.txt](prometheus_targets.txt) | Prometheus scrape targets: all 3 app instances + node-exporter, all reporting "up" |
| 15 | [alert_rules.txt](alert_rules.txt) | Prometheus alerting rules: HighErrorRate, HighLatency, InstanceDown, HighMemoryUsage, DatabaseDown, CacheMissRateHigh |
| 16 | [alertmanager_config.txt](alertmanager_config.txt) | Alertmanager configuration with webhook receiver routing alerts to the webhook-receiver service |
| 17 | [grafana_dashboard_panels.txt](grafana_dashboard_panels.txt) | Grafana dashboard panels: Request Rate, Error Rate, Latency percentiles, Active URLs, URLs Created, Redirects, Cache Hit Ratio, Instance Health |
