import os
import tempfile

import pytest
from peewee import SqliteDatabase

_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)

TEST_DB = SqliteDatabase(_DB_PATH, pragmas={"foreign_keys": 0})

MODELS = []


def _get_models():
    if not MODELS:
        from app.models.user import User
        from app.models.url import URL
        from app.models.event import Event

        MODELS.extend([User, URL, Event])
    return MODELS


def _bind_proxy():
    from app.database import db as db_proxy

    db_proxy.initialize(TEST_DB)


@pytest.fixture(scope="session")
def app():
    import app.database as db_module

    original = db_module.init_db

    def _test_init_db(flask_app):
        _bind_proxy()

        @flask_app.before_request
        def _db_connect():
            _bind_proxy()
            TEST_DB.connect(reuse_if_open=True)

        @flask_app.teardown_appcontext
        def _db_close(exc):
            pass

    db_module.init_db = _test_init_db
    _bind_proxy()
    TEST_DB.connect(reuse_if_open=True)

    from app import create_app

    flask_app = create_app(testing=True)
    db_module.init_db = original
    _bind_proxy()

    yield flask_app

    if not TEST_DB.is_closed():
        TEST_DB.close()
    for p in [_DB_PATH, _DB_PATH + "-wal", _DB_PATH + "-shm", _DB_PATH + "-journal"]:
        if os.path.exists(p):
            try:
                os.unlink(p)
            except OSError:
                pass


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def db_setup(app):
    _bind_proxy()
    models = _get_models()
    if TEST_DB.is_closed():
        TEST_DB.connect()
    TEST_DB.drop_tables(models, safe=True)
    TEST_DB.create_tables(models, safe=True)
    yield
    TEST_DB.drop_tables(models, safe=True)
    TEST_DB.create_tables(models, safe=True)
