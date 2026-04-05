"""Tests for the /metrics Prometheus endpoint."""


def test_metrics_endpoint_returns_200(client):
    """The /metrics endpoint should be accessible and return prometheus data."""
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_endpoint_returns_prometheus_content_type(client):
    """The /metrics response uses the Prometheus content type."""
    resp = client.get("/metrics")
    assert "text/plain" in resp.content_type or "text/plain" in resp.headers.get(
        "Content-Type", ""
    )


def test_metrics_contains_standard_counters(client):
    """The /metrics output includes the custom counters we defined."""
    # Make a request first so counters have data
    client.get("/health")
    resp = client.get("/metrics")
    body = resp.get_data(as_text=True)
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


def test_metrics_contains_business_counters(client):
    """The /metrics output includes business-specific counters."""
    resp = client.get("/metrics")
    body = resp.get_data(as_text=True)
    assert "urls_created_total" in body
    assert "redirects_total" in body


def test_metrics_contains_active_urls_gauge(client):
    """The /metrics output includes the active_urls gauge."""
    # Create a URL so the gauge has a meaningful value
    client.post("/urls", json={"url": "https://gauge-test.example.com"})
    resp = client.get("/metrics")
    body = resp.get_data(as_text=True)
    assert "active_urls" in body
