"""MongoDB (Atlas) connection via PyMongo. Collection names match the original Mongoose models."""
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient

log = logging.getLogger("newssphere.db")

_state = {"client": None, "db": None}

# Mongoose pluralised the original model names – keep the same collections so existing Atlas data keeps working.
USERS = "users"
ARTICLES = "articles"
BOOKMARKS = "bookmarks"
LIKES = "likes"
HISTORY = "readinghistories"
SUBSCRIBERS = "subscribers"


def init_db(uri=None, client=None):
    """Connect to MongoDB Atlas (or use an injected client – used by the test-suite)."""
    if client is None:
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Copy .env.example to .env and paste your MongoDB Atlas connection string."
            )
        client = MongoClient(uri, serverSelectionTimeoutMS=15000, appname="newssphere-flask")
        client.admin.command("ping")  # fail fast with a clear error if Atlas is unreachable
    _state["client"] = client
    try:
        db = client.get_default_database(default="newssphere")
    except Exception:  # pragma: no cover - older drivers
        db = client["newssphere"]
    _state["db"] = db
    ensure_indexes(db)
    return db


def get_db():
    if _state["db"] is None:
        raise RuntimeError("Database not initialised")
    return _state["db"]


def ensure_indexes(db):
    try:
        db[USERS].create_index("email", unique=True)
        a = db[ARTICLES]
        a.create_index([("publishedAt", DESCENDING)])
        a.create_index([("category", ASCENDING), ("publishedAt", DESCENDING)])
        a.create_index([("views", DESCENDING)])
        a.create_index([("popularityScore", DESCENDING)])
        a.create_index("tags")
        a.create_index([("isBreaking", ASCENDING), ("publishedAt", DESCENDING)])
        a.create_index("sourceUrl", unique=True, sparse=True)
        db[BOOKMARKS].create_index([("user", ASCENDING), ("article", ASCENDING)], unique=True)
        db[BOOKMARKS].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
        db[LIKES].create_index([("user", ASCENDING), ("article", ASCENDING)], unique=True)
        db[LIKES].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
        db[HISTORY].create_index([("userId", ASCENDING), ("readAt", DESCENDING)])
        db[HISTORY].create_index([("userId", ASCENDING), ("articleId", ASCENDING)])
        db[SUBSCRIBERS].create_index("email", unique=True)
    except Exception as exc:  # index creation must never stop the site from starting
        log.warning("Could not create indexes: %s", exc)
