"""Application configuration. Every secret comes from the environment (.env) – nothing is hard-coded."""
import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = _bool("FLASK_DEBUG", False)

    MONGODB_URI = os.getenv("MONGODB_URI", "").strip()

    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
    JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
    JWT_EXPIRES_DAYS = int(os.getenv("JWT_EXPIRES_DAYS", "7"))

    CLIENT_URL = os.getenv("CLIENT_URL", "http://localhost:5000").strip()

    # optional external news (server side only – keys never reach the browser)
    NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()
    RSS_FEEDS = os.getenv("RSS_FEEDS", "").strip()

    # seed sample articles + demo accounts automatically when the articles collection is empty
    SEED_ON_EMPTY = _bool("SEED_ON_EMPTY", True)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * int(os.getenv("JWT_EXPIRES_DAYS", "7"))
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    @classmethod
    def finalize(cls):
        if not cls.SECRET_KEY:
            warnings.warn(
                "SECRET_KEY is not set – using a temporary random key. Sessions will be reset on every restart. "
                "Set SECRET_KEY in .env.",
                RuntimeWarning,
            )
            cls.SECRET_KEY = secrets.token_hex(32)
        if not cls.JWT_SECRET:
            cls.JWT_SECRET = cls.SECRET_KEY
        return cls
