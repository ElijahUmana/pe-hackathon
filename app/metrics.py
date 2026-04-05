import time

from flask import request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Request metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Business metrics
URLS_CREATED = Counter("urls_created_total", "Total URLs created")
REDIRECTS_TOTAL = Counter("redirects_total", "Total redirects served")
CACHE_HITS = Counter("cache_hits_total", "Total cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total cache misses")

# Gauges
ACTIVE_URLS = Gauge("active_urls", "Number of active URLs")


_SKIP_METRICS_PATHS = frozenset({"/metrics", "/health"})


def init_metrics(app):
    """Initialize Prometheus metrics middleware."""

    @app.before_request
    def _start_timer():
        if request.path not in _SKIP_METRICS_PATHS:
            request._start_time = time.time()

    @app.after_request
    def _record_metrics(response):
        if request.path in _SKIP_METRICS_PATHS:
            return response

        latency = time.time() - getattr(request, "_start_time", time.time())
        endpoint = request.endpoint or "unknown"

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(latency)

        return response

    _gauge_cache = {"active_urls": 0, "last_updated": 0}

    @app.route("/metrics")
    def metrics():
        from flask import Response

        # Update active_urls gauge at most once per 30 seconds
        now = time.time()
        if now - _gauge_cache["last_updated"] > 30:
            try:
                from app.models.url import URL
                _gauge_cache["active_urls"] = URL.select().where(URL.is_active == True).count()  # noqa: E712
                _gauge_cache["last_updated"] = now
            except Exception:
                pass
        ACTIVE_URLS.set(_gauge_cache["active_urls"])

        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
