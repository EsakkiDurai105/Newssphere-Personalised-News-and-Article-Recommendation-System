"""Small shared helpers: errors, ids, dates, JSON serialisation, cache, validation."""
import re
import time
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from utils.constants import CATEGORY_SLUGS


class ApiError(Exception):
    def __init__(self, status, message, errors=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors


def now():
    """Naive UTC datetime (what PyMongo stores/returns by default)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_oid(value, default=None):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return default


def valid_oid(value):
    return ObjectId.is_valid(str(value)) if value is not None else False


def iso(dt):
    """JS-style ISO string (…T12:00:00.000Z) so the browser's Date() parses it identically to the old API."""
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def jsonable(obj):
    """Recursively turn ObjectId -> str and datetime -> ISO string."""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return iso(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items() if k != "__v"}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    return obj


def hours_since(dt):
    if not isinstance(dt, datetime):
        return 0.0
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0.0, (now() - dt).total_seconds() / 3600.0)


def page_params(args, default=12, maximum=50):
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(args.get("limit", default))
    except (TypeError, ValueError):
        limit = default
    limit = min(maximum, max(1, limit))
    return page, limit, (page - 1) * limit


def paged(items, total, page, limit):
    return {
        "articles": items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": max(1, -(-total // limit)),
        "hasMore": page * limit < total,
    }


# ---------------------------------------------------------------- tiny TTL cache
_cache = {}


def cached(key, ttl_seconds, producer):
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    value = producer()
    _cache[key] = (time.time() + ttl_seconds, value)
    return value


def clear_cache(prefix=""):
    for k in [k for k in _cache if k.startswith(prefix)]:
        _cache.pop(k, None)


# ---------------------------------------------------------------- validation
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def is_email(value):
    return bool(EMAIL_RE.match(str(value or "").strip()))


def assert_valid(errors):
    if errors:
        first = next(iter(errors.values()))
        raise ApiError(400, first, errors)


def validate_register(body):
    name, email, password = body.get("name"), body.get("email"), body.get("password")
    errors = {}
    if not name or len(str(name).strip()) < 2:
        errors["name"] = "Please enter your name (at least 2 characters)."
    if not email or not is_email(email):
        errors["email"] = "Please enter a valid email address."
    pw = str(password or "")
    if len(pw) < 8:
        errors["password"] = "Password must be at least 8 characters."
    elif not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        errors["password"] = "Password must contain at least one letter and one number."
    assert_valid(errors)


def validate_login(body):
    errors = {}
    if not body.get("email") or not is_email(body.get("email")):
        errors["email"] = "Please enter a valid email address."
    if not body.get("password"):
        errors["password"] = "Please enter your password."
    assert_valid(errors)


def sanitize_interests(interests):
    if not isinstance(interests, list):
        raise ApiError(400, "Interests must be a list of categories.")
    out = []
    for i in interests:
        s = str(i).lower()
        if s in CATEGORY_SLUGS and s not in out:
            out.append(s)
    return out


def regex_escape(s):
    return re.escape(str(s))


def safe_next(url, default="/"):
    """Only allow same-site relative redirects."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return default
