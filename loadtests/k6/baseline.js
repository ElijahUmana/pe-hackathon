import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// Custom metrics
const errorRate = new Rate("errors");
const redirectLatency = new Trend("redirect_latency");

// Bronze: 50 concurrent users
export const options = {
  stages: [
    { duration: "30s", target: 50 }, // Ramp up to 50 users
    { duration: "2m", target: 50 },  // Hold at 50 users
    { duration: "30s", target: 0 },  // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<3000"], // p95 < 3s
    errors: ["rate<0.05"],            // Error rate < 5%
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:80";

export function setup() {
  // Create a test user
  const userRes = http.post(
    `${BASE_URL}/users`,
    JSON.stringify({ username: `loadtest_${Date.now()}`, email: `loadtest_${Date.now()}@test.com` }),
    { headers: { "Content-Type": "application/json" } }
  );

  let userId = null;
  if (userRes.status === 201) {
    userId = JSON.parse(userRes.body).id;
  }

  // Create some test URLs
  const shortCodes = [];
  for (let i = 0; i < 10; i++) {
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/test/${i}`,
        user_id: userId,
        title: `Load Test URL ${i}`,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    if (res.status === 201) {
      shortCodes.push(JSON.parse(res.body).short_code);
    }
  }

  return { userId, shortCodes };
}

export default function (data) {
  const { shortCodes } = data;

  // Mix of operations weighted by real-world usage:
  // 70% redirects, 15% reads, 10% creates, 5% health checks
  const rand = Math.random();

  if (rand < 0.70 && shortCodes.length > 0) {
    // Redirect (most common operation)
    const code = shortCodes[Math.floor(Math.random() * shortCodes.length)];
    const res = http.get(`${BASE_URL}/${code}`, { redirects: 0 });
    check(res, {
      "redirect status is 302": (r) => r.status === 302,
    });
    errorRate.add(res.status !== 302);
    redirectLatency.add(res.timings.duration);
  } else if (rand < 0.85) {
    // List URLs
    const res = http.get(`${BASE_URL}/urls?per_page=10`);
    check(res, {
      "list status is 200": (r) => r.status === 200,
    });
    errorRate.add(res.status !== 200);
  } else if (rand < 0.95) {
    // Create URL
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/load/${Date.now()}/${Math.random()}`,
        title: "Load Test Created",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, {
      "create status is 201": (r) => r.status === 201,
    });
    errorRate.add(res.status !== 201);
  } else {
    // Health check
    const res = http.get(`${BASE_URL}/health`);
    check(res, {
      "health status is 200": (r) => r.status === 200,
    });
    errorRate.add(res.status !== 200);
  }

  sleep(0.5);
}
