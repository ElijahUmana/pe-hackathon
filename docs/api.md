# API Reference

Base URL: `http://localhost` (Docker Compose) or `http://localhost:5000` (local dev)

All request bodies must use `Content-Type: application/json`. All responses return JSON unless otherwise noted.

---

## Health & Metrics

### GET /health

Returns the application health status including database connectivity.

**Response: 200 OK**
```json
{
  "status": "ok",
  "database": "connected"
}
```

**Response: 200 OK (degraded)**
```json
{
  "status": "degraded",
  "database": "disconnected"
}
```

The endpoint always returns 200 -- check the `status` field to determine actual health. `degraded` means the database is unreachable but the application process is running.

---

### GET /metrics

Returns Prometheus-format metrics for scraping. Not intended for direct consumption.

**Response: 200 OK**
```
Content-Type: text/plain; version=0.0.4; charset=utf-8

# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="redirect_short_url",method="GET",status="302"} 1547.0
# HELP http_request_duration_seconds HTTP request latency in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="redirect_short_url",le="0.005",method="GET"} 823.0
...
# HELP active_urls Number of active URLs
# TYPE active_urls gauge
active_urls 1847.0
# HELP urls_created_total Total URLs created
# TYPE urls_created_total counter
urls_created_total 2031.0
# HELP redirects_total Total redirects served
# TYPE redirects_total counter
redirects_total 1547.0
# HELP cache_hits_total Total cache hits
# TYPE cache_hits_total counter
cache_hits_total 1203.0
# HELP cache_misses_total Total cache misses
# TYPE cache_misses_total counter
cache_misses_total 344.0
```

**Exposed metrics:**

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency (buckets: 5ms to 10s) |
| `urls_created_total` | Counter | -- | Total URLs created |
| `redirects_total` | Counter | -- | Total redirect operations |
| `cache_hits_total` | Counter | -- | Redis cache hits |
| `cache_misses_total` | Counter | -- | Redis cache misses |
| `active_urls` | Gauge | -- | Current count of active URLs |

---

## Users

### GET /users

List users with pagination.

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `page` | integer | 1 | -- | Page number |
| `per_page` | integer | 25 | 100 | Results per page |

**Request:**
```
GET /users?page=1&per_page=10
```

**Response: 200 OK**
```json
[
  {
    "id": 1,
    "username": "warmharvest01",
    "email": "warmharvest01@example.com",
    "created_at": "2025-08-11T22:29:20"
  },
  {
    "id": 2,
    "username": "warmriver24",
    "email": "warmriver24@relay.cloud",
    "created_at": "2025-02-16T04:28:39"
  }
]
```

---

### GET /users/:id

Get a single user by ID.

**Request:**
```
GET /users/1
```

**Response: 200 OK**
```json
{
  "id": 1,
  "username": "warmharvest01",
  "email": "warmharvest01@example.com",
  "created_at": "2025-08-11T22:29:20"
}
```

**Response: 404 Not Found**
```json
{
  "error": "User not found"
}
```

---

### POST /users

Create a new user.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | string | Yes | Unique username |
| `email` | string | Yes | Unique, valid email address |

**Request:**
```
POST /users
Content-Type: application/json

{
  "username": "janedoe",
  "email": "jane@example.com"
}
```

**Response: 201 Created**
```json
{
  "id": 5,
  "username": "janedoe",
  "email": "jane@example.com",
  "created_at": "2026-04-04T12:00:00"
}
```

**Response: 400 Bad Request**
```json
{
  "error": "username is required"
}
```

```json
{
  "error": "Invalid email format"
}
```

**Response: 409 Conflict**
```json
{
  "error": "Username already exists"
}
```

```json
{
  "error": "Email already exists"
}
```

---

### PUT /users/:id

Update an existing user. Only include fields you want to change.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | string | No | New username |
| `email` | string | No | New email address |

**Request:**
```
PUT /users/5
Content-Type: application/json

{
  "email": "jane.doe@example.com"
}
```

**Response: 200 OK**
```json
{
  "id": 5,
  "username": "janedoe",
  "email": "jane.doe@example.com",
  "created_at": "2026-04-04T12:00:00"
}
```

**Response: 404 Not Found**
```json
{
  "error": "User not found"
}
```

**Response: 400 Bad Request**
```json
{
  "error": "email cannot be empty"
}
```

**Response: 409 Conflict**
```json
{
  "error": "Username or email already exists"
}
```

---

### DELETE /users/:id

Permanently delete a user. This is a hard delete.

**Request:**
```
DELETE /users/1
```

**Response: 204 No Content**

(Empty body)

**Response: 404 Not Found**
```json
{
  "error": "User not found"
}
```

---

## URLs

### GET /urls

List shortened URLs with pagination.

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `page` | integer | 1 | -- | Page number |
| `per_page` | integer | 25 | 100 | Results per page |

**Request:**
```
GET /urls?page=1&per_page=5
```

**Response: 200 OK**
```json
[
  {
    "id": 1,
    "user_id": 1,
    "short_code": "ENE3UF",
    "original_url": "https://relay.cloud/harbor/garden/1",
    "title": "Launch deck zenith",
    "is_active": false,
    "created_at": "2025-08-18T05:25:03",
    "updated_at": "2025-10-08T12:48:37"
  },
  {
    "id": 2,
    "user_id": 150,
    "short_code": "MTOGkL",
    "original_url": "https://seeded.app/opal/trail/2",
    "title": "Incident notes quartz",
    "is_active": true,
    "created_at": "2025-10-30T20:22:45",
    "updated_at": "2026-01-18T19:28:15"
  }
]
```

---

### GET /urls/:id

Get a single URL by ID.

**Request:**
```
GET /urls/2
```

**Response: 200 OK**
```json
{
  "id": 2,
  "user_id": 150,
  "short_code": "MTOGkL",
  "original_url": "https://seeded.app/opal/trail/2",
  "title": "Incident notes quartz",
  "is_active": true,
  "created_at": "2025-10-30T20:22:45",
  "updated_at": "2026-01-18T19:28:15"
}
```

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

---

### POST /urls

Create a new shortened URL. A random 6-character alphanumeric short code is generated using cryptographically secure randomness.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | Original URL (must be valid HTTP/HTTPS) |
| `user_id` | integer | No | ID of the user who owns this URL |
| `title` | string | No | Descriptive title for the URL |

**Request:**
```
POST /urls
Content-Type: application/json

{
  "url": "https://example.com/my-long-page",
  "user_id": 1,
  "title": "My Example Page"
}
```

**Response: 201 Created**
```json
{
  "id": 2001,
  "user_id": 1,
  "short_code": "aB3xYz",
  "original_url": "https://example.com/my-long-page",
  "title": "My Example Page",
  "is_active": true,
  "created_at": "2026-04-04T12:00:00",
  "updated_at": "2026-04-04T12:00:00"
}
```

A `created` event is automatically recorded.

**Response: 400 Bad Request**
```json
{
  "error": "url is required"
}
```

```json
{
  "error": "A valid HTTP or HTTPS URL is required"
}
```

```json
{
  "error": "Content-Type must be application/json"
}
```

```json
{
  "error": "user_id must be an integer"
}
```

**Response: 404 Not Found**
```json
{
  "error": "User not found"
}
```

**Response: 500 Internal Server Error**
```json
{
  "error": "Failed to generate unique short code"
}
```

This only occurs if all 10 attempts to generate a unique code collide, which is statistically negligible with 62^6 (56.8 billion) possible codes.

**Important behaviors:**
- Submitting the same URL twice produces two different short codes (each URL gets a unique code every time).
- URLs without `http://` or `https://` schemes are rejected.
- Single words like `"google"` are rejected as invalid URLs.
- The `user_id` is validated against the users table if provided.

---

### PUT /urls/:id

Update an existing URL. Only include fields you want to change.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | No | New original URL (must be valid HTTP/HTTPS) |
| `title` | string | No | New title (or `null`/empty to clear) |
| `is_active` | boolean | No | Active status |

**Request:**
```
PUT /urls/2001
Content-Type: application/json

{
  "url": "https://example.com/updated-page",
  "is_active": false
}
```

**Response: 200 OK**
```json
{
  "id": 2001,
  "user_id": 1,
  "short_code": "aB3xYz",
  "original_url": "https://example.com/updated-page",
  "title": "My Example Page",
  "is_active": false,
  "created_at": "2026-04-04T12:00:00",
  "updated_at": "2026-04-04T12:05:00"
}
```

An `updated` event is recorded for each field that changed. The Redis cache for this short code is invalidated.

**Response: 400 Bad Request**
```json
{
  "error": "A valid HTTP or HTTPS URL is required"
}
```

```json
{
  "error": "is_active must be a boolean"
}
```

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

---

### DELETE /urls/:id

Soft-delete a URL by setting `is_active` to `false`. The record remains in the database but will no longer redirect.

**Request:**
```
DELETE /urls/2001
```

**Response: 204 No Content**

(Empty body)

A `deleted` event is recorded. The Redis cache for this short code is invalidated.

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

---

### GET /urls/:id/stats

Get redirect statistics for a URL.

**Request:**
```
GET /urls/2/stats
```

**Response: 200 OK**
```json
{
  "url": {
    "id": 2,
    "user_id": 150,
    "short_code": "MTOGkL",
    "original_url": "https://seeded.app/opal/trail/2",
    "title": "Incident notes quartz",
    "is_active": true,
    "created_at": "2025-10-30T20:22:45",
    "updated_at": "2026-01-18T19:28:15"
  },
  "redirect_count": 47
}
```

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

---

### GET /urls/:id/events

Get the event history for a specific URL.

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `page` | integer | 1 | -- | Page number |
| `per_page` | integer | 25 | 100 | Results per page |

**Request:**
```
GET /urls/2/events?page=1&per_page=5
```

**Response: 200 OK**
```json
[
  {
    "id": 3421,
    "url_id": 2,
    "user_id": 150,
    "event_type": "redirect",
    "timestamp": "2026-04-04T11:30:00",
    "details": "{\"ip\": \"192.168.1.1\", \"user_agent\": \"Mozilla/5.0\"}"
  },
  {
    "id": 2,
    "url_id": 2,
    "user_id": 150,
    "event_type": "created",
    "timestamp": "2025-10-30T20:22:45",
    "details": "{\"short_code\": \"MTOGkL\", \"original_url\": \"https://seeded.app/opal/trail/2\"}"
  }
]
```

Events are returned in reverse chronological order (newest first).

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

---

## Redirect

### GET /:short_code

Redirect to the original URL. This is the core operation of the URL shortener.

**Request:**
```
GET /aB3xYz
```

**Response: 302 Found**
```
Location: https://example.com/my-long-page
X-Cache: HIT
```

or

```
Location: https://example.com/my-long-page
X-Cache: MISS
```

The `X-Cache` header indicates whether the URL was served from Redis cache (`HIT`) or from the database (`MISS`).

**Behavior:**
1. Check Redis cache for `url:{short_code}`
2. On cache hit: redirect immediately, log redirect event
3. On cache miss: query PostgreSQL for an active URL with this short code
4. If found: cache the result in Redis with 600-second TTL, log redirect event, redirect
5. If not found (or inactive): return 404, no event logged

A `redirect` event is always recorded for successful redirects, capturing the client IP and User-Agent.

**Response: 404 Not Found**
```json
{
  "error": "URL not found"
}
```

Inactive (soft-deleted) URLs return 404. No event is logged for 404 responses.

---

## Events

### GET /events

List all events across all URLs.

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `page` | integer | 1 | -- | Page number |
| `per_page` | integer | 25 | 100 | Results per page |
| `type` | string | -- | -- | Filter by event type (`created`, `redirect`, `updated`, `deleted`) |

**Request:**
```
GET /events?type=redirect&page=1&per_page=5
```

**Response: 200 OK**
```json
[
  {
    "id": 3422,
    "url_id": 45,
    "user_id": 12,
    "event_type": "redirect",
    "timestamp": "2026-04-04T11:45:00",
    "details": "{\"ip\": \"10.0.0.1\", \"user_agent\": \"curl/8.0\"}"
  }
]
```

Events are returned in reverse chronological order (newest first).

**Event Types:**

| Type | When Created | Details Payload |
|---|---|---|
| `created` | URL is created via POST /urls | `{"short_code": "...", "original_url": "..."}` |
| `redirect` | A short URL is accessed via GET /:short_code | `{"ip": "...", "user_agent": "..."}` |
| `updated` | URL is updated via PUT /urls/:id | `{"field": "...", "new_value": "..."}` |
| `deleted` | URL is soft-deleted via DELETE /urls/:id | `{"reason": "user_requested"}` |

---

## Global Error Responses

These error responses can be returned by any endpoint:

**400 Bad Request**
```json
{
  "error": "Bad request"
}
```

**404 Not Found**
```json
{
  "error": "Not found"
}
```

**405 Method Not Allowed**
```json
{
  "error": "Method not allowed"
}
```

**500 Internal Server Error**
```json
{
  "error": "Internal server error"
}
```

---

## Pagination

All list endpoints support cursor-based pagination via `page` and `per_page` query parameters.

- `page` defaults to 1
- `per_page` defaults to 25, maximum is 100
- Values above 100 for `per_page` are silently capped to 100
- An empty array `[]` is returned when no results match or the page is beyond available data
