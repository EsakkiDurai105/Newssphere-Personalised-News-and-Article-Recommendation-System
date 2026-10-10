"""Test fixtures. Tests run against mongomock (an in-memory PyMongo stand-in) so no Atlas credentials are needed.
The production code path is identical – only the MongoClient is injected."""
import pytest
import mongomock

from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-test-secret-key-0123456789"
    JWT_SECRET = "test-jwt-secret-test-jwt-secret-0123456789"
    MONGODB_URI = ""
    SEED_ON_EMPTY = True
    NEWS_API_KEY = ""
    RSS_FEEDS = ""


@pytest.fixture()
def app():
    from app import create_app

    client = mongomock.MongoClient()
    return create_app(TestConfig, mongo_client=client)


@pytest.fixture()
def client(app):
    return app.test_client()


H = {"X-Requested-With": "fetch"}


@pytest.fixture()
def demo(client):
    r = client.post("/api/auth/login", json={"email": "demo@newssphere.com", "password": "Demo@12345"}, headers=H)
    assert r.status_code == 200, r.json
    return client
