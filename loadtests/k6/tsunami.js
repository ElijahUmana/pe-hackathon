import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("errors");
const redirectLatency = new Trend("redirect_latency");
const createLatency = new Trend("create_latency");

// Gold: 500+ concurrent users / 100+ req/sec
export const options = {
  stages: [
    { duration: "30s", target: 100 },  // Warm up
    { duration: "30s", target: 250 },  // Ramp
    { duration: "30s", target: 500 },  // Ramp to 500
    { duration: "3m", target: 500 },   // Hold at 500 — tsunami
    { duration: "1m", target: 600 },   // Push beyond
    { duration: "30s", target: 0 },    // Cool down
  ],
  thresholds: {
    http_req_duration: ["p(95)<5000"],  // p95 < 5s under extreme load
    errors: ["rate<0.05"],              // Error rate < 5% (Gold requirement)
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:80";

export function setup() {
  const shortCodes = [];
  for (let i = 0; i < 50; i++) {
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/tsunami/${i}`,
        title: `Tsunami Test URL ${i}`,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    if (res.status === 201) {
      shortCodes.push(JSON.parse(res.body).short_code);
    }
  }
  return { shortCodes };
}

export default function (data) {
  const { shortCodes } = data;
  const rand = Math.random();

  if (rand < 0.80 && shortCodes.length > 0) {
    // 80% redirects — this is what caching optimizes
    const code = shortCodes[Math.floor(Math.random() * shortCodes.length)];
    const res = http.get(`${BASE_URL}/${code}`, { redirects: 0 });
    check(res, { "redirect 302": (r) => r.status === 302 });
    errorRate.add(res.status !== 302);
    redirectLatency.add(res.timings.duration);
  } else if (rand < 0.90) {
    const res = http.get(`${BASE_URL}/urls?per_page=5`);
    check(res, { "list 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  } else if (rand < 0.97) {
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/t/${Date.now()}/${Math.random()}`,
        title: "Tsunami Created",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, { "create 201": (r) => r.status === 201 });
    errorRate.add(res.status !== 201);
    createLatency.add(res.timings.duration);
  } else {
    const res = http.get(`${BASE_URL}/health`);
    check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  }

  sleep(0.1); // Minimal sleep for maximum throughput
}
