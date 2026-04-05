import logging
import os
import sys

from pythonjsonlogger import json as jsonlogger


def setup_logging(app):
    """Configure structured JSON logging."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Remove default Flask/werkzeug handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # JSON formatter
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )

    # Stream handler to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Configure root logger
    logging.root.addHandler(handler)
    logging.root.setLevel(getattr(logging, log_level, logging.INFO))

    # Reduce noise from werkzeug
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # Add request logging — skip high-traffic paths to reduce I/O overhead
    _skip_log_paths = frozenset({"/metrics", "/health"})

    @app.after_request
    def log_request(response):
        from flask import request
        if request.path in _skip_log_paths:
            return response
        # Skip logging redirects (short_code paths) — they're 70-80% of traffic
        # and logging each one adds ~0.5ms of I/O overhead per request
        if response.status_code == 302:
            return response
        logger = logging.getLogger("app.request")
        logger.info(
            "Request processed",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", ""),
            },
        )
        return response

    return app
