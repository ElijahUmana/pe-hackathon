import logging

from dotenv import load_dotenv
from flask import Flask, jsonify

from app.database import db, init_db
from app.logging_config import setup_logging
from app.metrics import init_metrics
from app.routes import register_routes


def create_app(testing=False):
    load_dotenv()

    app = Flask(__name__)
    app.config["TESTING"] = testing

    # Structured JSON logging
    setup_logging(app)

    # Database
    init_db(app)

    # Import models to register them with Peewee
    from app.models import URL, Event, User  # noqa: F401

    # Create tables if they don't exist
    with app.app_context():
        try:
            db.connect(reuse_if_open=True)
            db.create_tables([User, URL, Event], safe=True)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Table creation skipped: {e}")
        finally:
            if not db.is_closed():
                db.close()

    # Routes
    register_routes(app)

    # Prometheus metrics
    init_metrics(app)

    # Pre-warm Redis cache with active URLs (skip during testing)
    if not testing:
        try:
            from app.cache import warm_cache

            warm_cache(app)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Cache warm-up skipped: {e}")

    # Health check
    @app.route("/health")
    def health():
        health_status = {"status": "ok"}
        try:
            db.connect(reuse_if_open=True)
            db.execute_sql("SELECT 1")
            health_status["database"] = "connected"
        except Exception:
            health_status["database"] = "disconnected"
            health_status["status"] = "degraded"
        return jsonify(health_status)

    # Global error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logging.getLogger(__name__).error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request"}), 400

    return app
