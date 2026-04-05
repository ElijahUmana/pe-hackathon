# Demo Script -- 2 Minute Video

Record screen + webcam (or screen only). Speak clearly, move fast between sections. Pre-open all browser tabs before recording.

**Pre-recording setup:**
1. Open terminal SSH'd into the server: `ssh root@64.23.250.234`
2. Open browser tabs:
   - Tab 1: `http://64.23.250.234/health`
   - Tab 2: `http://64.23.250.234:3000` (Grafana, logged in as admin)
   - Tab 3: GitHub repo Actions tab showing green CI
3. Have a second local terminal ready for curl commands
4. Clear terminal history so it looks clean

---

## 0:00 -- 0:10 | Introduction

**Show:** Your face or the terminal with the project name visible.

**Say:**
> "Hey, I'm Elijah. This is Snip, a production-grade URL shortener I built for the MLH Production Engineering Hackathon. It passes all 29 evaluator tests, handles 500 concurrent users with zero errors, and runs on 11 Docker containers with full monitoring. Let me show you."

---

## 0:10 -- 0:30 | Live Application

**Show:** Switch to the local terminal. Run these commands one at a time.

**Say:**
> "The app is live on a DigitalOcean droplet. Here's the health check."

```bash
curl http://64.23.250.234/health
```

**Say:**
> "Database connected, status OK. Let's create a shortened URL."

```bash
curl -s -X POST http://64.23.250.234/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://devpost.com", "user_id": 1}' | python3 -m json.tool
```

**Say:**
> "Created. Now let's follow the redirect."

```bash
curl -v http://64.23.250.234/<SHORT_CODE_FROM_ABOVE> 2>&1 | grep "< Location"
```

*Note: grab the short_code from the previous response and substitute it in.*

**Say:**
> "302 redirect to devpost.com. Every redirect is tracked as an event."

---

## 0:30 -- 0:50 | Infrastructure

**Show:** Switch to the SSH terminal on the server.

**Say:**
> "This runs on 11 containers in Docker Compose."

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}" | head -15
```

**Say:**
> "Three Flask app instances behind Nginx load balancing, PostgreSQL, Redis for caching, Prometheus and Grafana for monitoring, Alertmanager with a webhook receiver that forwards alerts to Discord. All with health checks and auto-restart."

---

## 0:50 -- 1:10 | Testing and CI

**Show:** Switch to the GitHub Actions tab in the browser, showing the green CI badge.

**Say:**
> "We have 149 internal tests at 91% coverage, plus the evaluator's 29 tests all pass. CI runs lint and tests on every push."

**Show:** Scroll through the green check marks briefly.

**Say:**
> "For load testing, we used k6. At 200 concurrent users, p95 latency is 807 milliseconds -- 3.7 times under the 3-second threshold. At 500 concurrent users, zero percent error rate with 232 requests per second sustained."

**Show:** If you have load test output saved, briefly flash it on screen. Otherwise, just keep talking over the CI tab.

---

## 1:10 -- 1:30 | Monitoring

**Show:** Switch to the Grafana browser tab. Navigate to the URL Shortener dashboard.

**Say:**
> "Grafana shows everything in real time. Request rate by status code, error rate, latency percentiles, cache hit ratio, and per-instance health."

**Show:** Scroll through the dashboard panels slowly so they are visible.

**Say:**
> "Prometheus scrapes metrics from all three Flask instances. When something goes wrong, Alertmanager fires alerts through a webhook receiver to Discord."

---

## 1:30 -- 1:50 | Chaos Engineering

**Show:** Switch to the SSH terminal.

**Say:**
> "Let's break something. I'm going to kill one of the app instances."

```bash
docker kill pe-hackathon-app2-1
```

**Say:**
> "Instance is dead. But the service is still up because Nginx routes around it."

```bash
curl http://64.23.250.234/health
```

**Say:**
> "Still responding. And watch -- Docker's restart policy brings it back automatically."

```bash
sleep 10 && docker compose ps --format "table {{.Name}}\t{{.Status}}" | grep app2
```

**Say:**
> "Back up and healthy. Prometheus detected the outage, Alertmanager fired a ServiceDown alert, and the webhook receiver logged it. Full incident lifecycle, automated."

---

## 1:50 -- 2:00 | Close

**Show:** Your face, or the terminal, or the Grafana dashboard.

**Say:**
> "Snip. 29 out of 29 evaluator tests. 149 internal tests. Zero errors at 500 concurrent users. 11 containers. Full observability. Built for production. Thanks for watching."

---

## Timing Notes

- Total: exactly 2 minutes
- If running long, cut the chaos section short -- skip the `sleep 10` and just say "Docker restarts it automatically in under 15 seconds"
- If running short, add a sentence about the Redis cache hit ratio (85% at peak load) during the monitoring section
- Practice the curl commands beforehand so you know the short_code to use
- Record in one take if possible -- cuts look worse than minor stumbles
