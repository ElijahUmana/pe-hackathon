import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("errors");
const redirectLatency = new Trend("redirect_latency");

// Silver: 200 concurrent users
export const options = {
  stages: [
    { duration: "30s", target: 50 },   // Warm up
    { duration: "30s", target: 100 },  // Ramp to 100
    { duration: "30s", target: 200 },  // Ramp to 200
    { duration: "3m", target: 200 },   // Hold at 200
    { duration: "30s", target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<3000"], // p95 < 3s (Silver requirement)
    errors: ["rate<0.05"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:80";

export function setup() {
  const shortCodes = [];
  for (let i = 0; i < 20; i++) {
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/scale/${i}`,
        title: `Scale Test URL ${i}`,
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

  if (rand < 0.75 && shortCodes.length > 0) {
    const code = shortCodes[Math.floor(Math.random() * shortCodes.length)];
    const res = http.get(`${BASE_URL}/${code}`, { redirects: 0 });
    check(res, { "redirect 302": (r) => r.status === 302 });
    errorRate.add(res.status !== 302);
    redirectLatency.add(res.timings.duration);
  } else if (rand < 0.85) {
    const res = http.get(`${BASE_URL}/urls?per_page=10`);
    check(res, { "list 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  } else if (rand < 0.95) {
    const res = http.post(
      `${BASE_URL}/urls`,
      JSON.stringify({
        url: `https://example.com/s/${Date.now()}/${Math.random()}`,
        title: "Scale Created",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, { "create 201": (r) => r.status === 201 });
    errorRate.add(res.status !== 201);
  } else {
    const res = http.get(`${BASE_URL}/health`);
    check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  }

  sleep(0.3);
}
