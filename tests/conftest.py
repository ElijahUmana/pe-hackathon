import pytest
from peewee import SqliteDatabase

from app.database import db as db_proxy


MODELS = []


def _get_models():
    """Lazily import models so the proxy is already initialized."""
    if not MODELS:
        from app.models.user import User
        from app.models.url import URL
        from app.models.event import Event

        MODELS.extend([User, URL, Event])
    return MODELS


@pytest.fixture(scope="session")
def app():
    """Create a Flask test app backed by an in-memory SQLite database."""
    # Initialize the DatabaseProxy with SQLite BEFORE creating the Flask app.
    test_db = SqliteDatabase(":memory:")
    db_proxy.initialize(test_db)

    # Now import create_app.  Its init_db call will try to re-initialize with
    # PostgreSQL, so we monkey-patch init_db to be a no-op for the test session.
    import app.database as db_module

    _original_init_db = db_module.init_db

    def _test_init_db(flask_app):
        """Skip PostgreSQL setup; just register the before_request / teardown hooks."""

        @flask_app.before_request
        def _db_connect():
            db_proxy.connect(reuse_if_open=True)

        @flask_app.teardown_appcontext
        def _db_close(exc):
            if not db_proxy.is_closed():
                db_proxy.close()

    db_module.init_db = _test_init_db

    from app import create_app

    flask_app = create_app(testing=True)

    # Restore original init_db so it doesn't leak into non-test code.
    db_module.init_db = _original_init_db

    return flask_app


@pytest.fixture(scope="session")
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def db_setup():
    """Create all tables before each test and drop them after."""
    models = _get_models()
    db_proxy.connect(reuse_if_open=True)
    db_proxy.create_tables(models)
    yield
    db_proxy.drop_tables(models)
    if not db_proxy.is_closed():
        db_proxy.close()
