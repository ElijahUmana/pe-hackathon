// MLH PE Hackathon Submission Auto-Fill Script
// Open browser console (Cmd+Option+J) on the submission page and paste this

(function() {
  const urlInputs = document.querySelectorAll('input[placeholder="https://..."]');
  const noteAreas = document.querySelectorAll('textarea[placeholder="What this evidence shows..."]');

  const data = [
    // RELIABILITY BRONZE (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/health_endpoint.txt", note: 'GET /health returns {"status":"ok","database":"connected"}. Live at http://64.23.250.234/health' },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/pytest_results.txt", note: "184 tests passing across 12 test files covering models, routes, validators, edge cases, and full API contract" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/actions", note: "GitHub Actions CI runs on every push to every branch. Lints with ruff, runs pytest with coverage gate at 70%" },
    // RELIABILITY SILVER (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/coverage_report.txt", note: "91% code coverage (threshold: 70%). Per-file breakdown shows 93-100% on all route handlers" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/tests/test_integration.py", note: "Full flow integration tests: create user -> create URL -> redirect -> verify events. Also test_api_contract.py with 35 evaluator-spec tests" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/troubleshooting.md", note: "Error Handling Behavior section documents JSON-only responses for 400, 404, 405, 500. Also see docs/failure-modes.md" },
    // RELIABILITY GOLD (4)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/coverage_report.txt", note: "91% coverage, 184 tests. CI enforces --cov-fail-under=70" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/error_handling.txt", note: "6 error scenarios: missing fields, invalid URL, non-JSON body, nonexistent resource, bad user_id, wrong HTTP method. All return clean JSON" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/reliability/auto_restart_proof.txt", note: "Container killed, health check still passes via remaining instances, Docker restart policy auto-recovers. See also evidence/reliability/failed_ci_proof.txt" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/failure-modes.md", note: "400-line failure mode analysis covering all 11 components: impact matrix, cascading scenarios, recovery times" },
    // DOCUMENTATION BRONZE (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/README.md", note: "324-line README with architecture diagram, quick start for local and Docker, performance table, tech stack" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/architecture.md", note: "624 lines: Mermaid component diagram, ER diagram, data flow sequences, security considerations, monitoring pipeline" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/api.md", note: "752-line full API reference: every endpoint with method, path, request/response examples, error codes" },
    // DOCUMENTATION SILVER (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/deployment.md", note: "635 lines: DigitalOcean setup, Docker Compose deployment, zero-downtime rolling restart, rollback procedure, smoke test checklist" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/troubleshooting.md", note: "415 lines: app won't start, high latency, container restart loops, OOM, port conflicts, DB issues, Redis issues, CI failures" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/environment-variables.md", note: "Every env var documented: DATABASE_*, REDIS_URL, LOG_LEVEL, FLASK_DEBUG, DISCORD_WEBHOOK_URL, GF_SECURITY_*" },
    // DOCUMENTATION GOLD (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/runbook.md", note: "576-line runbook: alert-response procedures, PromQL queries, recovery verification checklists, communication protocol, post-incident template" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/decision-log.md", note: "14 technical decisions with rationale: Flask, Peewee, PostgreSQL, Redis, Nginx, Docker Compose, Gunicorn, Prometheus+Grafana, k6, webhook receiver" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/capacity-plan.md", note: "307 lines: resource footprint, throughput estimates, scaling projections, cost-per-request ($0.04/million), SLA definition" },
    // SCALABILITY BRONZE (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/tree/main/loadtests/k6", note: "3 k6 scripts: baseline.js (50 VU), scaleout.js (200 VU), tsunami.js (500+ VU). Realistic traffic mix" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/screenshots/load_test_bronze.txt", note: "50 VU: 0% errors, p95=27ms, ~90 req/s" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/bottleneck-report.md", note: "254-line bottleneck report with pre/post optimization comparison, per-endpoint latency breakdown, cache analysis" },
    // SCALABILITY SILVER (4)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/k6_silver_200users.txt", note: "200 VU: p95=807ms (threshold <3s), error rate <5%. Full k6 terminal output" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/docker_ps_multi_instance.txt", note: "docker compose ps showing 3 Flask instances + Nginx + all supporting services (11 total)" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/nginx/nginx.conf", note: "Nginx with least_conn upstream across 3 Flask instances, keepalive 64, gzip, health caching" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/k6_silver_200users.txt", note: "p95=807ms at 200 VU — 3.7x under the 3-second threshold" },
    // SCALABILITY GOLD (4)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/k6_gold_500users.txt", note: "500-600 VU: p95=2.29s, 0% errors, 98,984 successful checks, 232+ req/s" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/cache_hit_miss_proof.txt", note: "X-Cache: MISS then HIT. Connection pool, 300s TTL, warm-up on startup. See app/cache.py" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/bottleneck-report.md", note: "Before: Silver p95=3,620ms FAIL, Gold 4.81% errors. After: pooling+indexes+keepalive -> Silver p95=807ms, Gold 0% errors" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/scalability/k6_gold_500users.txt", note: "0.00% error rate at 500-600 concurrent users. 100% of 98,984 checks passed" },
    // INCIDENT RESPONSE BRONZE (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/incident-response/json_logs.txt", note: 'python-json-logger output with timestamp, level, message, method, path, status, remote_addr, user_agent fields' },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/incident-response/metrics_endpoint.txt", note: "Prometheus: http_requests_total, latency histograms, cache_hits, redirects_total, active_urls. Live at http://64.23.250.234/metrics" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/evidence/incident-response/json_logs.txt", note: "Logs viewable via docker compose logs without SSH. Also aggregated in Grafana via Prometheus metrics" },
    // INCIDENT RESPONSE SILVER (3)
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/prometheus/alert_rules.yml", note: "10 alert rules: ServiceDown(15s), HighErrorRate(>10%), HighLatency(p95>2s), HighMemory, HostCPU, HostMemory, DiskLow/Critical, NetworkErrors, NodeExporterDown" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/alert-pipeline.md", note: "Prometheus -> Alertmanager -> Webhook Receiver -> Discord. Real ServiceDown alerts delivered to Discord channel" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/alert-pipeline.md", note: "ServiceDown fires after 15s, Alertmanager group_wait 5s. Total: ~25 seconds, well under 5-minute requirement" },
    // INCIDENT RESPONSE GOLD (3)
    { url: "http://64.23.250.234:3000", note: "Grafana: 8 panels - Request Rate, Error Rate, Latency p50/p95/p99, Active URLs, URLs Created, Redirects, Cache Hit Ratio, Instance Health. Login: admin/hackathon2026" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/runbook.md", note: "576-line runbook: step-by-step for each alert, PromQL queries, recovery checklists, communication protocol, post-incident template" },
    { url: "https://github.com/ElijahUmana/pe-hackathon/blob/main/docs/incident-diagnosis.md", note: "537-line Sherlock Mode: Flask instance failure diagnosed via Grafana panels, PromQL, structured logs. Full timeline detection to resolution" },
  ];

  let filled = 0;
  const setNativeValue = (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(
      el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };

  for (let i = 0; i < data.length && i < urlInputs.length; i++) {
    if (!urlInputs[i].value || urlInputs[i].value === 'https://...') {
      setNativeValue(urlInputs[i], data[i].url);
      filled++;
    }
    if (noteAreas[i] && (!noteAreas[i].value || noteAreas[i].value === 'What this evidence shows...')) {
      setNativeValue(noteAreas[i], data[i].note);
      filled++;
    }
  }

  console.log('Auto-fill complete: ' + filled + ' fields filled');
  alert('Done! Filled ' + filled + ' fields. Scroll through and review, then click Create Draft.');
})();
